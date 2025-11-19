# Notification

await EmailService.send_email(to="user@example.com", subject="Hi", body="Hello")

# SMS
await SMSService.send_sms(to="+1234567890", message="Your code: 123456")

# High-level
await NotificationService.send_welcome_email(email="...", username="...")


app/
├── utils/
│   ├── pagination.py
│   └── notifications.py
├── templates/
│   └── emails/
│       ├── welcome.html/txt
│       └── password_reset.html/txt
└── config/config.py (add settings)