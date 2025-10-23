import os, json, time, requests

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from .models import Message, Decision, Block
from .utils import sign, verify, hash_block_payload
from django.db import transaction
from django.db.models import Count
# add imports at top



NODE_ADDR = os.environ.get("NODE_ADDR") or "http://127.0.0.1:8000"
PEERS = [p for p in os.environ.get("PEERS", "").split(",") if p]
ALL_NODES = [NODE_ADDR] + PEERS

def n_f():
    n = len(ALL_NODES)
    f = (n - 1) // 3
    return n, f

def quorum():
    n, f = n_f()
    return 2 * f + 1

def broadcast(path, payload):
    for peer in ALL_NODES:
        try:
            requests.post(peer + path, json=payload, timeout=1)
        except Exception:
            pass

def save_message(phase, value, sender, timestamp, sig):
    Message.objects.get_or_create(
        phase=phase,
        value=value,
        sender=sender,
        defaults={"timestamp": timestamp, "signature": sig},
    )

def count_unique(phase, value):
    return Message.objects.filter(phase=phase, value=value).aggregate(c=Count("sender", distinct=True))["c"] or 0

@csrf_exempt
def propose(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST JSON only")
    data = json.loads(request.body)
    value = data.get("value")
    if not value:
        return HttpResponseBadRequest("need value")

    primary = ALL_NODES[0]
    if NODE_ADDR != primary:
        # forward to primary
        r = requests.post(primary + "/propose", json={"value": value})
        return JsonResponse({"forwarded_to": primary, "status": r.text})

    msg = {
        "phase": "PREPREPARE",
        "value": value,
        "sender": NODE_ADDR,
        "timestamp": time.time(),
    }
    msg["sig"] = sign(msg)
    save_message("PREPREPARE", value, NODE_ADDR, msg["timestamp"], msg["sig"])
    broadcast("/preprepare", msg)
    return JsonResponse({"status": "preprepare_broadcast", "value": value})

@csrf_exempt
def preprepare(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    msg = json.loads(request.body)
    sig = msg.pop("sig", None)
    sender = msg.get("sender")
    if not sig or not sender:
        return HttpResponseBadRequest("missing sig or sender")
    if not verify(msg, sig, settings.NODE_SECRET):
        return JsonResponse({"err": "bad signature"}, status=400)
    value = msg["value"]
    save_message("PREPREPARE", value, sender, msg["timestamp"], sig)

    # send PREPARE
    pmsg = {"phase": "PREPARE", "value": value, "sender": NODE_ADDR, "timestamp": time.time()}
    pmsg["sig"] = sign(pmsg)
    save_message("PREPARE", value, NODE_ADDR, pmsg["timestamp"], pmsg["sig"])
    broadcast("/prepare", pmsg)
    return JsonResponse({"status": "prepare_sent", "value": value})

@csrf_exempt
def prepare(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    msg = json.loads(request.body)
    sig = msg.pop("sig", None)
    sender = msg.get("sender")
    if not sig or not sender:
        return HttpResponseBadRequest("missing sig or sender")
    if not verify(msg, sig, settings.NODE_SECRET):
        return JsonResponse({"err": "bad signature"}, status=400)
    value = msg["value"]
    save_message("PREPARE", value, sender, msg["timestamp"], sig)

    if count_unique("PREPARE", value) >= quorum() and count_unique("COMMIT", value) == 0:
        cmsg = {"phase": "COMMIT", "value": value, "sender": NODE_ADDR, "timestamp": time.time()}
        cmsg["sig"] = sign(cmsg)
        save_message("COMMIT", value, NODE_ADDR, cmsg["timestamp"], cmsg["sig"])
        broadcast("/commit", cmsg)
    return JsonResponse({"status": "prepare_received", "value": value})

@csrf_exempt
def commit(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    msg = json.loads(request.body)
    sig = msg.pop("sig", None)
    sender = msg.get("sender")
    if not sig or not sender:
        return HttpResponseBadRequest("missing sig or sender")
    if not verify(msg, sig, settings.NODE_SECRET):
        return JsonResponse({"err": "bad signature"}, status=400)
    value = msg["value"]
    save_message("COMMIT", value, sender, msg["timestamp"], sig)

    if count_unique("COMMIT", value) >= quorum():
        created_decision, created = Decision.objects.get_or_create(value=value, defaults={"decided": True})
        # only the primary will propose chain blocks for decided values (simple demo rule)
        primary = ALL_NODES[0]
        if NODE_ADDR == primary and created:
            # create block using the next index and local tip
            tip_index, tip_hash = get_chain_tip()
            next_index = tip_index + 1
            block_payload = {
                "index": next_index,
                "value": value,
                "prev_hash": tip_hash,
                "timestamp": timezone.now().isoformat(),
                "proposer": NODE_ADDR,
            }
            block_payload["block_hash"] = hash_block_payload(block_payload)
            block_payload["signature"] = sign({k:block_payload[k] for k in ("index","value","prev_hash","timestamp","proposer")})
            # store locally
            Block.objects.get_or_create(
                index=block_payload["index"],
                defaults={
                    "value": block_payload["value"],
                    "prev_hash": block_payload["prev_hash"],
                    "proposer": block_payload["proposer"],
                    "signature": block_payload["signature"],
                    "block_hash": block_payload["block_hash"],
                }
            )
            # broadcast to peers
            broadcast_block(block_payload)

    return JsonResponse({"status": "commit_received", "value": value})

def status(request):
    value = request.GET.get("value")
    if not value:
        return HttpResponseBadRequest("need ?value=")
    decided = Decision.objects.filter(value=value, decided=True).exists()
    data = {
        "value": value,
        "preprepare_count": count_unique("PREPREPARE", value),
        "prepare_count": count_unique("PREPARE", value),
        "commit_count": count_unique("COMMIT", value),
        "decided": decided,
        "quorum": quorum(),
    }
    return JsonResponse(data)




# helper: get tip index & hash
def get_chain_tip():
    last = Block.objects.order_by("-index").first()
    if not last:
        return -1, None
    return last.index, last.block_hash

# endpoint to receive a block broadcast by proposer (primary)
@csrf_exempt
def block_receive(request):
    """
    POST /block
    Body: {
      "index": <int>,
      "value": "...",
      "prev_hash": "...",
      "timestamp": "<iso or epoch>",
      "proposer": "http://127.0.0.1:8000",
      "signature": "...",
      "block_hash": "..."
    }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    payload = json.loads(request.body)
    sig = payload.pop("signature", None)
    block_hash = payload.get("block_hash")
    proposer = payload.get("proposer")
    index = payload.get("index")
    prev_hash = payload.get("prev_hash")

    if not sig or not block_hash or index is None:
        return HttpResponseBadRequest("missing fields")

    # verify signature over canonical payload (signature was created by proposer)
    # For demo we assume same NODE_SECRET across nodes. In production map proposer->pubkey/secret.
    if not verify({k: payload[k] for k in ("index","value","prev_hash","timestamp","proposer")}, sig, settings.NODE_SECRET):
        return JsonResponse({"err": "bad block signature"}, status=400)

    # verify block_hash matches payload
    expected_hash = hash_block_payload({ "index": index, "value": payload["value"], "prev_hash": prev_hash, "timestamp": payload["timestamp"], "proposer": proposer })
    if expected_hash != block_hash:
        return JsonResponse({"err": "block_hash mismatch"}, status=400)

    # Ensure prev_hash matches local tip (simple linear chain)
    tip_index, tip_hash = get_chain_tip()
    if tip_hash is None and prev_hash not in (None, "", "null"):
        # new node starting but expects genesis; accept only if prev_hash empty
        return JsonResponse({"err": "missing genesis or prev_hash mismatch", "local_tip_index": tip_index, "local_tip_hash": tip_hash}, status=409)
    if tip_hash is not None and prev_hash != tip_hash:
        # chain divergence: request chain sync (simple approach: tell caller)
        return JsonResponse({"err": "prev_hash mismatch", "expected_prev_hash": tip_hash, "got_prev_hash": prev_hash}, status=409)

    # append to DB atomically (guard against duplicates)
    with transaction.atomic():
        created = False
        if not Block.objects.filter(index=index).exists():
            Block.objects.create(
                index=index,
                value=payload["value"],
                prev_hash=prev_hash,
                proposer=proposer,
                signature=sig,
                block_hash=block_hash
            )
            created = True
    return JsonResponse({"status": "appended" if created else "already_exists", "index": index})

# helper to broadcast block to nodes
def broadcast_block(block_payload):
    for peer in ALL_NODES:
        try:
            requests.post(peer + "/block", json=block_payload, timeout=1)
        except Exception:
            pass

    # in commit(): after you create Decision, add this block creation step (pseudo-snippet)
    # replace your earlier Decision creation block with the following adjustments:

def blocks_list(request):
    blocks = Block.objects.all().order_by("index")
    data = []
    for b in blocks:
        data.append({
            "index": b.index,
            "value": b.value,
            "prev_hash": b.prev_hash,
            "timestamp": b.timestamp.isoformat(),
            "proposer": b.proposer,
            "block_hash": b.block_hash,
        })
    return JsonResponse({"chain": data, "length": len(data)})
