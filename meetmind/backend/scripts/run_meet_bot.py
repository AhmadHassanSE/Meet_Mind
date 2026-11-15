"""Run one authorized Google Meet bot without starting web servers.

This opens a visible dedicated browser. Manual Google sign-in and host admission
may be required. Existing application DB is used unless MEETMIND_DB is set.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time

import httpx
from app import main


async def run(args):
    async with main.lifespan(main.app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://local') as api:
            response=await api.post('/api/meet/bots',json={'title':args.title,'meeting_url':args.meet_url,
                'display_name':args.name,'consent_confirmed':args.confirm_recording,'max_duration_minutes':args.minutes})
            response.raise_for_status();bot_id=response.json()['id']
            print('Bot session:',bot_id,flush=True)
            last=None;started=None
            try:
                deadline=time.monotonic()+args.minutes*60+600
                while time.monotonic()<deadline:
                    record=(await api.get('/api/meet/bots/'+bot_id)).json()
                    if record['state']!=last:
                        print(record['state']+': '+record['message'],flush=True);last=record['state']
                    if record['state']=='recording':
                        if started is None:started=time.monotonic()
                        if args.seconds and time.monotonic()-started>=args.seconds:
                            (await api.post('/api/meet/bots/'+bot_id+'/stop')).raise_for_status()
                    if record['state'] in {'completed','failed','cancelled'}:
                        Path('runs').mkdir(exist_ok=True)
                        Path('runs/live-bot-result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
                        if record.get('meeting_id'):print('Saved meeting:',record['meeting_id'],flush=True)
                        if record['state']!='completed':raise RuntimeError(record['message'])
                        return
                    await asyncio.sleep(1)
                raise TimeoutError('Bot run exceeded its time limit')
            finally:
                if bot_id in main.bot_manager.controls:main.bot_manager.command(bot_id,'cancel')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('meet_url')
    parser.add_argument('--title',default='Google Meet browser bot')
    parser.add_argument('--name',default='MeetMind Notetaker')
    parser.add_argument('--minutes',type=int,default=60)
    parser.add_argument('--seconds',type=int,help='Stop recording after this many seconds, for an authorized smoke check')
    parser.add_argument('--confirm-recording',action='store_true',help='Host/participants know audio will be recorded')
    args=parser.parse_args()
    asyncio.run(run(args))
