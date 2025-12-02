from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ChatMessage
import json

@login_required
def chat_room(request):
    return render(request, 'chat/room.html')

@login_required
def get_chat_messages(request):
    last_id = request.GET.get('last_id', 0)
    messages = ChatMessage.objects.filter(id__gt=last_id).select_related('user').order_by('created_at')
    
    data = [{
        'id': msg.id,
        'user': msg.user.username,
        'message': msg.message,
        'created_at': msg.created_at.strftime('%H:%M')
    } for msg in messages]
    
    return JsonResponse({'messages': data})

@login_required
@require_POST
def post_chat_message(request):
    try:
        data = json.loads(request.body)
        message_text = data.get('message')
        if message_text:
            msg = ChatMessage.objects.create(user=request.user, message=message_text)
            return JsonResponse({'status': 'ok', 'message_id': msg.id})
        return JsonResponse({'status': 'error', 'message': 'Empty message'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
