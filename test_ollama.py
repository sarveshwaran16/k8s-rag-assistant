import requests

resp = requests.post(
    'http://localhost:11434/api/generate',
    json={
        'model': 'phi3:mini',
        'prompt': 'Extract Kubernetes entities from: CrashLoopBackOff occurs when a pod fails. Reply only with JSON having entities and relationships keys.',
        'stream': False,
        'options': {'temperature': 0.0}
    },
    timeout=300
)
print(resp.json()['response'])