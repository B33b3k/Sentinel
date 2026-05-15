#!/usr/bin/env python3
"""Print active OTP sessions to terminal during demo."""
import json
import redis

r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
keys = r.keys("otp_pending:*")
if not keys:
    print("No pending OTPs.")
else:
    for k in keys:
        raw = r.get(k)
        if raw:
            d = json.loads(raw)
            print(f"tx={d['tx_id']}  acct={d['account_id']}  phone={d['customer_phone']}  email={d['customer_email']}")
            print(f"  SMS code : {d['sms_otp']}   Email code: {d['email_otp']}")
