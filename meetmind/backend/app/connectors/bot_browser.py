"""Visible, isolated browser participant. No login/CAPTCHA/admission bypass."""
import asyncio
import os
from pathlib import Path
import re
import time

HERE = Path(__file__).parent
EXTENSION = HERE.parents[2] / 'extension'
LEAVE = re.compile(r'leave call|leave meeting', re.I)
JOIN = re.compile(r'^(ask to join|join now|join meeting|join)$', re.I)
DENIED = re.compile(r"you can.t join this|couldn.t join|not allowed to join|someone removed you|you.ve been removed|you left the (?:meeting|call)|call ended|meeting (?:has )?ended|invalid meeting code|meeting code.*not.*valid|can.t find.*meeting", re.I)


class BotCancelled(Exception):
    pass


class BrowserBot:
    def __init__(self, profile, *, headless=False, channel=None):
        self.profile = Path(profile)
        self.headless = headless
        self.channel = channel or os.getenv('MEETMIND_BOT_BROWSER', 'chrome')
        self.context = self.page = self.playwright = None

    async def open(self, meeting_url, on_chunk):
        from playwright.async_api import async_playwright
        self.profile.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt': self.profile.chmod(0o700)
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(self.profile), channel=self.channel, headless=self.headless,
            locale='en-US', viewport={'width': 1280, 'height': 800},
            args=['--autoplay-policy=no-user-gesture-required'])
        self.context.set_default_timeout(4000)
        async def binding(source,data):
            await on_chunk(data)
        await self.context.expose_binding('__meetmindAudioChunk', binding)
        # The WebRTC hook must be installed before Meet creates peer connections.
        await self.context.add_init_script(path=str(HERE/'bot_audio.js'))
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        cdp = await self.context.new_cdp_session(self.page)
        # CDP grantPermissions grants the supplied list and rejects all others.
        await cdp.send('Browser.grantPermissions', {'permissions':[], 'origin':'https://meet.google.com'})
        await self.page.goto(meeting_url, wait_until='domcontentloaded', timeout=60000)

    async def visible(self, locator):
        return await locator.count() > 0 and await locator.first.is_visible()

    async def join(self, name, control, update, timeout=300):
        deadline = time.monotonic()+timeout
        requested = False
        last_state = None
        while time.monotonic() < deadline:
            if control.cancel.is_set() or control.stop.is_set(): raise BotCancelled()
            if self.page.is_closed(): raise RuntimeError('Bot browser was closed before admission')
            body = await self.page.locator('body').inner_text(timeout=4000)
            denied = DENIED.search(body)
            if denied: raise RuntimeError('Google Meet did not admit the bot: '+denied[0])
            if await self.visible(self.page.get_by_role('button', name=LEAVE)): return
            join = self.page.get_by_role('button', name=JOIN)
            if await self.visible(join) and not requested:
                name_input = self.page.get_by_role('textbox', name=re.compile('your name|name', re.I))
                if await self.visible(name_input): await name_input.first.fill(name)
                for pattern in ('turn off microphone', 'turn off camera'):
                    toggle = self.page.get_by_role('button', name=re.compile(pattern,re.I))
                    if await self.visible(toggle): await toggle.first.click()
                await join.first.click()
                requested = True
                state = 'waiting_for_admission'
            elif 'accounts.google.com' in self.page.url or not requested:
                state = 'needs_login'
            else: state = 'waiting_for_admission'
            if state != last_state:
                update(state, 'Sign in or resolve the Google prompt in the bot browser, then Continue.' if state=='needs_login'
                       else 'Join request sent. Waiting for the meeting host to admit the bot.')
                last_state = state
            if control.resume.is_set():
                control.resume.clear(); requested = False
            await asyncio.sleep(1)
        raise RuntimeError('Admission/sign-in timed out. The host must admit the bot; retry when the call is ready.')

    async def start_capture(self):
        for script in ('selectors.js','hints_core.js'):
            await self.page.add_script_tag(path=str(EXTENSION/script))
        captions = self.page.get_by_role('button', name=re.compile('turn on captions',re.I))
        if await self.visible(captions): await captions.first.click()
        return await self.page.evaluate('() => __meetmindBotAudio.start()')

    async def tick(self):
        if self.page.is_closed(): raise RuntimeError('Bot browser was closed during capture')
        return await self.page.evaluate('() => ({stats:__meetmindBotAudio.stats(), hints:__meetmindBotAudio.hints()})')

    async def ended(self):
        if self.page.is_closed(): return True
        body = await self.page.locator('body').inner_text(timeout=4000)
        return bool(DENIED.search(body))

    async def stop_capture(self):
        hints = await self.page.evaluate('() => __meetmindBotAudio.hints(true)')
        stats = await self.page.evaluate('() => __meetmindBotAudio.stop()')
        return stats, hints

    async def close(self):
        try:
            if self.page and not self.page.is_closed():
                leave = self.page.get_by_role('button', name=LEAVE)
                if await self.visible(leave): await leave.first.click(timeout=2000)
        except Exception:
            pass
        finally:
            try:
                if self.context: await self.context.close()
            finally:
                if self.playwright: await self.playwright.stop()
