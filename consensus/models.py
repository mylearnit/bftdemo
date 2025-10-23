from django.db import models

class Message(models.Model):
    PHASE_CHOICES = [
        ("PREPREPARE", "PREPREPARE"),
        ("PREPARE", "PREPARE"),
        ("COMMIT", "COMMIT"),
    ]
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES)
    value = models.CharField(max_length=255)
    sender = models.CharField(max_length=255)
    timestamp = models.FloatField()
    signature = models.CharField(max_length=128)

    class Meta:
        unique_together = ("phase", "value", "sender")

    def __str__(self):
        return f"{self.phase} {self.value} from {self.sender}"

class Decision(models.Model):
    value = models.CharField(max_length=255, unique=True)
    decided = models.BooleanField(default=False)
    decided_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.value} decided={self.decided}"

class Block(models.Model):
    index = models.BigIntegerField(unique=True)                       # block height (0,1,2...)
    value = models.CharField(max_length=255)                          # the decided value stored in this block (demo)
    prev_hash = models.CharField(max_length=128, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    proposer = models.CharField(max_length=255)                       # node that proposed this block (primary)
    signature = models.CharField(max_length=128)                      # HMAC signature of block payload
    block_hash = models.CharField(max_length=128, unique=True)       # SHA256 hex of canonical block payload

    class Meta:
        ordering = ["index"]

    def __str__(self):
        return f"Block#{self.index} {self.block_hash[:10]}... val={self.value}"
