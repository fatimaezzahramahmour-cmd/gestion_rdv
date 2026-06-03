import json
import logging
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncDate

from .models import Conversation, MessageChatbot, FAQDentaire
from .chatbot_engine import ChatbotEngine, MAX_MESSAGE_LENGTH

logger = logging.getLogger('rdv.chatbot')

FALLBACK_REPONSE = (
    "Desole, je n'ai pas pu traiter votre demande. "
    "Reformulez ou contactez le cabinet."
)


@csrf_exempt
@require_http_methods(["POST"])
def api_chat_message(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        logger.warning('Chatbot: JSON invalide')
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    try:
        message_texte = (data.get('message') or '').strip()
        session_id = (data.get('session_id') or '').strip()

        if not message_texte:
            return JsonResponse({'success': False, 'error': 'Message vide'}, status=400)

        if len(message_texte) > MAX_MESSAGE_LENGTH:
            message_texte = message_texte[:MAX_MESSAGE_LENGTH]

        if not session_id or len(session_id) > 100:
            session_id = str(uuid.uuid4())

        conversation = _get_or_create_conversation(request, session_id)

        MessageChatbot.objects.create(
            conversation=conversation, role='user', contenu=message_texte,
        )

        utilisateur = request.user if request.user.is_authenticated else None
        engine = ChatbotEngine(conversation)
        resultat = engine.generer_reponse(message_texte, utilisateur=utilisateur)

        reponse = (resultat.get('reponse') or '').strip()
        if not reponse:
            logger.error(
                'Chatbot reponse vide apres generer_reponse session=%s intention=%s',
                session_id[:12], resultat.get('intention'),
            )
            reponse = FALLBACK_REPONSE

        msg_bot = MessageChatbot.objects.create(
            conversation=conversation,
            role='assistant',
            contenu=reponse,
            intention_detectee=resultat.get('intention', ''),
            confiance=resultat.get('confiance', 0.0),
            sources_utilisees=resultat.get('sources', []),
        )

        conversation.save()

        logger.info(
            'Chatbot OK session=%s intention=%s confiance=%.2f len=%d',
            session_id[:12],
            resultat.get('intention'),
            resultat.get('confiance', 0.0),
            len(reponse),
        )

        return JsonResponse({
            'success': True,
            'reponse': reponse,
            'intention': resultat.get('intention'),
            'action': resultat.get('action'),
            'suggestions': resultat.get('suggestions', []),
            'confiance': resultat.get('confiance'),
            'conversation_id': conversation.id,
            'session_id': session_id,
            'timestamp': msg_bot.created_at.isoformat(),
        })

    except Exception:
        logger.exception('Chatbot: erreur inattendue')
        return JsonResponse({
            'success': False,
            'error': 'Erreur interne du chatbot',
            'reponse': FALLBACK_REPONSE,
        }, status=500)


def api_chat_history(request):
    session_id = (request.GET.get('session_id') or '').strip()
    if not session_id:
        return JsonResponse({'success': False, 'error': 'session_id requis'}, status=400)

    try:
        conversation = Conversation.objects.filter(
            session_id=session_id, statut='active',
        ).first()

        if not conversation:
            return JsonResponse({'success': True, 'messages': [], 'conversation_id': None})

        messages = conversation.messages.values(
            'role', 'contenu', 'created_at', 'intention_detectee',
        ).order_by('created_at')

        return JsonResponse({
            'success': True,
            'messages': list(messages),
            'conversation_id': conversation.id,
            'contexte': conversation.contexte,
        })
    except Exception:
        logger.exception('Chatbot: erreur historique session=%s', session_id[:12])
        return JsonResponse({'success': False, 'error': 'Erreur historique'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_chat_feedback(request):
    try:
        data = json.loads(request.body or '{}')
        message_id = data.get('message_id')
        utile = data.get('utile', True)
        logger.info(
            'Chatbot feedback message_id=%s utile=%s',
            message_id, utile,
        )
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception:
        logger.exception('Chatbot: erreur feedback')
        return JsonResponse({'success': False, 'error': 'Erreur feedback'}, status=500)


@login_required
def chatbot_stats(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Acces interdit'}, status=403)

    total_conversations = Conversation.objects.count()
    total_messages = MessageChatbot.objects.count()
    messages_aujourd_hui = MessageChatbot.objects.filter(
        created_at__date=timezone.localtime().date(),
    ).count()

    top_intentions = MessageChatbot.objects.filter(
        role='assistant', intention_detectee__isnull=False,
    ).exclude(intention_detectee='').values('intention_detectee').annotate(
        count=Count('id'),
    ).order_by('-count')[:10]

    conversations_par_jour = Conversation.objects.filter(
        created_at__gte=timezone.localtime() - timezone.timedelta(days=7),
    ).annotate(date=TruncDate('created_at')).values('date').annotate(
        count=Count('id'),
    ).order_by('date')

    top_faqs = FAQDentaire.objects.order_by('-compteur_utilisation')[:10]

    return JsonResponse({
        'success': True,
        'stats': {
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'messages_aujourd_hui': messages_aujourd_hui,
            'top_intentions': list(top_intentions),
            'conversations_par_jour': [
                {'date': c['date'].isoformat(), 'count': c['count']}
                for c in conversations_par_jour
            ],
            'top_faqs': [
                {'question': f.question, 'utilisations': f.compteur_utilisation}
                for f in top_faqs
            ],
        },
    })


def _get_or_create_conversation(request, session_id):
    user = request.user if request.user.is_authenticated else None
    conversation = Conversation.objects.filter(
        session_id=session_id, statut='active',
    ).first()

    if conversation:
        if user and not conversation.utilisateur:
            conversation.utilisateur = user
            conversation.save(update_fields=['utilisateur'])
        return conversation

    return Conversation.objects.create(
        session_id=session_id, utilisateur=user, contexte={'source': 'widget_web'},
    )
