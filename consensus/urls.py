from django.urls import path
from . import views

urlpatterns = [
    path("propose", views.propose),
    path("preprepare", views.preprepare),
    path("prepare", views.prepare),
    path("commit", views.commit),
    path("status", views.status),
    path("block", views.block_receive),          # POST to append a block
    path("blocks", views.blocks_list),           # GET chain
]