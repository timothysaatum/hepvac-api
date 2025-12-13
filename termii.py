import requests

url = "https://api.ng.termii.com/api/sender-id/request"

payload = {
    "api_key": "TLrsTzpEKLaScEnDdsgDTPVgaSHliKMVRjVgWlwlsMuKkgGEmPwKiClZkJYJAr",  # replace after regenerating
    "sender_id": "Drive",
    "use_case": "Send vaccination reminders to patients",
    "company": "Drive Diag"
}

headers = {
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)

print(response.status_code)
print(response.text)
