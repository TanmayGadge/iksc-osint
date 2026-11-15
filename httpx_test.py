import httpx
import json
from dotenv import load_dotenv
import os
import subprocess

load_dotenv()

def send_requests():
    with httpx.Client() as client:
        resp = client.post("https://reqres.in/api/user", json={
            "name": "Tanmay",
            "job": "AI Engineer"
        },
        headers={
            "x-api-key": os.getenv("REQRES_API_KEY", "")
        }
        )

        with open('./api_test_output.json', 'r', encoding='utf-8') as file:
            log_file = json.load(file)
            # json_output = json.dumps(resp.json(), indent=4)
            log_file['logs'].append(resp.json())
            file.close()
            
        with open('./api_test_output.json', 'w', encoding='utf-8') as file:
            json.dump(log_file, file, indent=4)
            file.close()
            # print("Logs updated successfully!")
            
        # user_input = input("See log file? (y/n): ").lower()
        # if user_input == "y":
        #     with open('./api_test_output.json', 'r', encoding="utf-8") as file:
        #         print(file.read())
        #     # subprocess.run(["cat", "api_test_output.json"], capture_output=True, text=True, check=True, shell=True)
        # else:
        #     print("Exiting...")
        #     os._exit(1)
        
for i in range(int(input("How may requests?: "))):
    send_requests()
print("execution complete")