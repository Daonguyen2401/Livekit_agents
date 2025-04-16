import requests

url = "https://ce5f-1-53-240-222.ngrok-free.app/webhook/invoke_chat"
params = {
    "chatInput": "Do I have any schedule tomorrow"
}

response = requests.get(
            url,
            params=params,
        )
data = response.json()
output = data.get("output")
print(output)