# Django BFT Blockchain Demo

A minimal **Byzantine Fault Tolerant consensus** system with a simple blockchain built using **Django + Python**.

Each node runs a Django instance. They agree on proposed values using a simplified PBFT flow (`propose → preprepare → prepare → commit`), then the primary node adds each decided value as a block and broadcasts it.

---

## 🚀 Quick Start

```bash
# 1. Clone and install
git clone https://github.com/mylearnit/bftdemo.git
cd bftdemo
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Run migrations
python manage.py migrate

# 3. Start multiple nodes (each on different ports)
NODE_ADDR=http://127.0.0.1:8000 ALL_NODES="http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002" python manage.py runserver 8000
NODE_ADDR=http://127.0.0.1:8001 ALL_NODES="http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002" python manage.py runserver 8001
NODE_ADDR=http://127.0.0.1:8002 ALL_NODES="http://127.0.0.1:8000,http://127.0.0.1:8001,http://127.0.0.1:8002" python manage.py runserver 8002


# 4. Propose a Value
curl -X POST http://127.0.0.1:8000/propose -H "Content-Type: application/json" \
     -d '{"value": "hello world"}'

# 5.Check blockchains
curl http://127.0.0.1:8002/blocks | jq
```