# Gmail sending

Approved follow-up emails are sent from the **approver's own Gmail account**. MeetMind requests only the `gmail.send` permission (plus `openid email`, to show which account is connected). It cannot read or delete mail.

## How sending is controlled

- A draft can be sent only while its approval is valid: the exact recipients, subject, body and source commitment that were approved, under the current policy. If two approvals are required, both must be given.
- Sending happens either from the meeting workflow's **execute** step or with **Send now** on an approved draft. Only the approver or the meeting organizer can press Send now.
- Each draft is reserved before sending and sent **at most once**. Repeating a request returns the original Gmail message id.
- Delivery states:
  - `sent`, with the Gmail message id and sender address;
  - `failed`, with the reason;
  - `not_configured`, when the approver has not connected Gmail. Nothing is sent in this case.
- Temporary Google errors (429 and 5xx) are retried up to 3 times with backoff. An expired access token is refreshed once. Other errors stop immediately.
- If the server stops in the middle of a send, the draft is marked failed with "check the Sent folder" rather than resent automatically.
- Sender selection:
  - With `require sender approver` in the policy, only the approver's account is used.
  - Otherwise the person who requested the draft may also be the sender, if the approver has not connected Gmail.
- Connect, disconnect and every delivery are recorded in the audit log and the draft history.
- Refresh tokens are encrypted at rest (Fernet) with `MEETMIND_SECRET_KEY`, or with a local `<database>.secret.key` file that is gitignored. They are never returned by the API. Disconnecting revokes the token at Google.

## One-time setup (team)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Gmail API**.
2. On the **OAuth consent screen**:
   - choose *External*;
   - keep it in **Testing**;
   - add the scope `.../auth/gmail.send`;
   - add every team Gmail address under **Test users**.

   Apps in testing mode with listed test users need no Google verification.
3. Under **Credentials**, create an *OAuth client ID* of type **Web application** with this authorised redirect URI:
   `http://127.0.0.1:8000/api/integrations/gmail/callback`
4. Start the backend with:

   ```powershell
   $env:MEETMIND_GOOGLE_CLIENT_ID='<client id>'
   $env:MEETMIND_GOOGLE_CLIENT_SECRET='<client secret>'
   $env:MEETMIND_SECRET_KEY='<output of: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">'
   # Optional: MEETMIND_GOOGLE_REDIRECT_URI, MEETMIND_UI_URL (default http://127.0.0.1:5173)
   ```

   Never commit these values.
5. Each user opens **Account → Gmail → Connect Gmail**, signs in, and allows sending.

## Tests

`tests/test_gmail.py` simulates Google's endpoints. It covers:
- the OAuth flow with PKCE and a single-use state;
- refusing a connection without send permission;
- the encrypted token never appearing in responses or plaintext;
- sending exactly once from the approver's account;
- blocking unapproved or edited drafts;
- other users being unable to send;
- the not-connected case;
- retry, refresh and permanent failure;
- revoke on disconnect;
- interrupted-send recovery.

A live send through the meeting workflow succeeded on 15 Nov 2026 (Gmail message id `1a1de13bdd37be42`); see `docs/development-evidence.md`.
