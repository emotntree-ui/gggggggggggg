# Guild-Glory / DRIFT — API Upgrade

## इस पैकेज में क्या बदला

- खाली Stub API हटाकर Transactions, Groups, Activity Log, Inbox, Notifications, Alerts और Push Subscription के लिए persistent JSON storage जोड़ा गया।
- Frontend में इस्तेमाल हो रहे missing routes जोड़े: `/api/buyCredits`, transaction cancel/order ID, group actions, inbox actions, public contact info, group refetch और progression endpoints।
- Client launch अब `group_id` देता है और group/activity history रिकॉर्ड करता है।
- Admin वेबसाइट में **Payments** टैब जोड़ा गया; वहाँ pending payment request approve/reject हो सकती है।
- Signup route अब `signup.html` पर खुलता है।
- Bot account management, logs, stats और clan-control APIs अब admin session मांगते हैं।
- Admin के लिए hard-coded `DG DRIFT / DG DRIFT` पासवर्ड हटाया गया। पहली बार शुरू करते समय random bootstrap password console में आएगा, या `ADMIN_PASSWORD` environment variable दें।
- मोबाइल स्क्रीन और reduced-motion के लिए CSS सुधार जोड़े।
- साझा किए जाने वाले सोर्स में वास्तविक account/password/token/device/coupon data खाली कर दिया गया है। अपना निजी data केवल अपने स्थानीय backup से वापस रखें।

## चलाना

1. Python 3.10+ इस्तेमाल करें।
2. `pip install -r requirements.txt`
3. `.env.example` की कॉपी `.env` नाम से बनाकर सेटिंग्स भरें। Python अपने-आप `.env` लोड नहीं करता; Android/Termux में चलाने से पहले environment export करें।
4. पहले से प्रोजेक्ट की तरह `python app.py` चलाएँ। मौजूदा `app.py` में वेब पोर्ट `20333` है।
5. ब्राउज़र में `http://127.0.0.1:20333/login` खोलें। यदि `ADMIN_PASSWORD` सेट नहीं है तो पहली बार के console output से random password लें।

## Payment सुरक्षा

यह build किसी payment gateway से स्वतः verify नहीं करता। `/api/buyCredits` केवल pending request बनाता है और कोई credit नहीं जोड़ता। Admin को payment अलग से verify करके ही Payments टैब से approve करना चाहिए। Approval पर credits जोड़े जाते हैं। किसी भी order ID को अकेले payment proof न मानें।

## Web Push

Subscription `/api/push/subscribe` में सुरक्षित रूप से persist होती है। असली push delivery के लिए VAPID keypair और delivery worker/provider अभी configure करना आवश्यक है; बिना key के API `configured: false` लौटाएगी।

## Added / repaired API routes

- `GET /api/transactions`
- `POST /api/buyCredits`
- `POST /api/transaction/cancel`
- `POST /api/transaction/update-order-id`
- `GET /api/admin/transactions`
- `POST /api/admin/transaction/verify`
- `GET /api/client/groups`
- `POST /api/client/group-action`
- `POST /api/admin/group-action`
- `GET /api/client/activity-log`
- `GET /api/client/refetch-clan-data?group_id=...`
- `GET /api/client/glory-progression?group_id=...`
- `GET /api/inbox/messages`
- `POST /api/inbox/mark-read`
- `POST /api/inbox/mark-all-read`
- `POST /api/inbox/dismiss`
- `GET /api/notifications`
- `GET /api/client/active-alert`
- `POST /api/client/dismiss-alert`
- `GET /api/vapid-public-key`
- `POST /api/push/subscribe`
- `GET /api/public/contact-info`

Empty lists mean no saved records yet; they no longer represent hard-coded placeholder handlers. Clan data refresh currently returns stored data because no separate refresh provider is configured. Existing game protocol/bypass logic was not upgraded.

## एडमिन लॉगिन ठीक नहीं हो रहा हो

1. सर्वर बंद करें।
2. इस फ़ोल्डर में चलाएँ: `python reset_admin.py`
3. Admin username डालें (आमतौर पर `admin`) और नया पासवर्ड दो बार डालें। पासवर्ड टर्मिनल में दिखाई नहीं देगा।
4. फिर `python app.py` से सर्वर शुरू करें और `/login` पर उसी username/password से लॉगिन करें।
5. `users.json` में यूज़र डेटा सुरक्षित रखें; यह स्क्रिप्ट चुने हुए एडमिन का रोल/पासवर्ड बदलती है, बाकी यूज़र नहीं हटाती।

वैकल्पिक: सर्वर शुरू करने से पहले `ADMIN_USERNAME` और `ADMIN_PASSWORD` environment variables सेट करें। अगर चुना हुआ admin पहले से मौजूद है, तो स्पष्ट रूप से सेट किया गया `ADMIN_PASSWORD` अब उसका पासवर्ड रीसेट करेगा।


## Pricing API और Clan Launch Approval (अपडेट)

### Pricing API कैसे चेक करें
- वेबसाइट में लॉगिन के बाद क्लाइंट pricing region selector से कीमत लोड करता है।
- सीधे जाँचने के लिए सर्वर चलने पर `http://127.0.0.1:20333/api/pricing` खोलें। यह JSON में `basic_credit_inr`, `premium_credit_inr` और enabled regions लौटाता है।
- टर्मिनल से: `curl -i http://127.0.0.1:20333/api/pricing`
- यह endpoint सार्वजनिक है; इसलिए लॉगिन की जरूरत नहीं। कीमतें अभी कॉन्फ़िगरेशन में निर्धारित हैं, किसी payment provider से लाइव नहीं आतीं।

### Clan Launch Approval का नया तरीका
1. यूज़र के पास पर्याप्त credit हो तो Client में Clan ID/UID और Region भरकर launch request भेजता है। एक credit अस्थायी रूप से काटा जाता है।
2. अनुरोध `groups.json` में `status: awaiting_approval` के साथ सेव होता है। अब admin की मंजूरी से पहले clan-join worker शुरू नहीं होता।
3. Admin Panel → `Clan Launch Approvals` में Username, Clan UID/ID, Region, Credit type और Request ID दिखाई देंगे।
4. `Approve` दबाने पर अनुरोध स्वीकार होता है और clan-join worker कतार में जाता है। `Reject + Refund` दबाने पर अनुरोध अस्वीकार होता है और एक credit वापस किया जाता है।
5. API: `GET /api/admin/groups` (admin session आवश्यक) और `POST /api/admin/group-approval` JSON body `{"group_id":"GRP-...","decision":"approve"}` या `decision":"reject"` के साथ।

### टेस्टिंग
- Pricing: `GET /api/pricing` — HTTP 200 और JSON देखें।
- Admin launch queue: admin login के बिना `GET /api/admin/groups` को HTTP 401 देना चाहिए; admin session के साथ JSON list देनी चाहिए।
- Approval: केवल `awaiting_approval` वाली request approve/reject हो सकती है; दुबारा action करने पर HTTP 409 मिलेगा।
- नए बदलावों में Python syntax (`py_compile`) और admin page inline JavaScript syntax जाँची गई है। वास्तविक game server/account पर clan join सफलता की गारंटी नहीं है।


## My Groups visibility patch

- Added the missing `renderGroups()` function so the My Groups panel can render API results instead of throwing a JavaScript ReferenceError.
- Requests now show pending approval, approved/processing, active, failed, rejected, and cancelled states, along with request ID, clan ID, region, timestamps, review admin, credit tier, and per-account request results when available.
- Join results are saved against the correct user/request; raw tokens are never included in the stored result rows. A server exception now marks the request failed instead of leaving it stuck in processing.
- Added a Refresh Clan Data button. It queries the clan detail endpoint using the local token cache, stores only the parsed fields (not raw response bytes), and records Guild XP snapshots when the API returns them. The API field is Guild XP; this should not be represented as verified in-game Glory if the game API does not provide that value.
- `GET /api/client/glory-progression` now returns the latest snapshot and the delta between saved snapshots.

### Deploy / test

1. Stop the old server and back up your current folder.
2. Extract this ZIP into a new folder. Restore only your own `token_cache.json` or account data from a trusted local backup if live clan data is needed; these files are intentionally blank in the package. Never share tokens.
3. Install the project's `requirements.txt` if needed and start using your usual launch command.
4. Sign in as a normal test user, launch a group, and confirm it appears immediately under My Groups with `Pending Approval`.
5. Approve it in Admin → Clan Launch Approvals, then refresh My Groups. Account-level results appear after the worker finishes. Click Refresh Clan Data to query available clan details.

Validation performed: Python syntax compilation and JavaScript syntax check. Live game-server calls and live browser/login behavior have not been tested in this environment. A successful HTTP 200 for a join request is displayed as “Request accepted”, not as proof of confirmed clan membership.


## INR Pricing / Payment Provider Status (2026-10-26)
- Basic credit: ₹149; Premium credit: ₹1,799.
- Public pricing card updated to INR.
- Binance-specific checkout UI and deep-link handlers removed.
- Payment requests still remain pending for admin review; this source does NOT yet have a live FamPay/FamePay merchant API integration. Do not claim automatic verification.
- Before enabling live checkout, confirm the exact provider and use its official merchant API docs/credentials stored server-side in environment variables. Never put secret keys in HTML.


## INR / UPI Checkout Upgrade (2026-10-26)
- Fixed stale visible prices in the Buy Credits card (old UI showed ₹1.70 / ₹20.00 even though the API returned different prices). All visible Basic/Premium price defaults now match the server: ₹149 / ₹1,799 per credit.
- Removed leftover crypto ticker text (USDT/USDC/BUSD/DAI/FDUSD) from the payment translation.
- Purchase now creates a pending transaction first. If `UPI_RECEIVER_ID` is configured on the server, the modal shows a UPI intent link with the exact INR amount and unique transaction reference. User enters UTR after payment; duplicate UTRs are rejected.
- Payment is not auto-verified: UPI intent opening or a user-submitted UTR is not proof. Admin must verify the actual payment before credits are added.
- Configure `UPI_RECEIVER_ID` and `UPI_RECEIVER_NAME` in the server environment (or copy the entries from `.env.example` into your launch environment). Do not paste API secrets into HTML.
- This is a UPI intent checkout that may open FamPay if installed and supported; it is NOT a direct official Famepay.in/FamPay merchant API integration. That requires the merchant's official API docs and credentials.


### UPI चालू करने का आसान तरीका
1. `payment_config.example.json` की कॉपी बनाकर उसका नाम `payment_config.json` रखें।
2. उसमें `upi_receiver_id` में अपना सही receiving UPI ID और `upi_receiver_name` में प्राप्तकर्ता का नाम भरें।
3. सर्वर restart करें और Buy Credits खोलें। भुगतान लिंक तभी दिखेगा जब UPI ID वैध हो।
4. भुगतान के बाद UTR दर्ज करें। एडमिन बैंक/UPI ऐप में वास्तविक भुगतान देखकर ही Approve करे।

`payment_config.json` को सार्वजनिक वेबसाइट पर डाउनलोड करने योग्य न रखें; यह सर्वर रूट में है और static files के रूप में serve नहीं होना चाहिए। इस प्रोजेक्ट का static root केवल `DRIFT/` है।


## Admin Panel Upgrade (QR + Bot Account Controls)
- Admin → **Account Tools**: UPI ID, receiver name, और direct JPG/PNG QR URL सेट करें। Save करने के बाद QR user payment modal में दिखेगा।
- Admin → **Bot Accounts**: `[{"uid":"123456789","password":"..."}]` या `[{"token":"..."}]` पूरा JSON paste करके Save करें। यह `accounts.json` में merge/update होगा।
- हर account पर Start / Stop / Restart / Delete और ऊपर Start All / Stop All / Restart All / Delete All मौजूद हैं।
- QR image दिखना payment verification नहीं है; UTR/बैंक रिकॉर्ड जाँचकर ही payment approve करें।
- UPI ID की environment variable (`UPI_RECEIVER_ID`) config file के UPI ID को override करती है।
