from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_room, name='room'),
    path('api/messages/', views.get_chat_messages, name='get_messages'),
    path('api/post/', views.post_chat_message, name='post_message'),
]
