import logging
import re
import random
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher

from django.utils import timezone

from .forms import get_creneaux_disponibles, cabinet_local_today, cabinet_day_datetime_bounds, rdv_datetime_cabinet
from .models import Conversation, FAQDentaire, Rendez_vous, Service

logger = logging.getLogger('rdv.chatbot')

MAX_MESSAGE_LENGTH = 2000

# Libellés cliquables pour le patient (markdown → liens dans le widget)
LIEN_CONNEXION = '[Se connecter à mon compte](/login/)'
LIEN_RDV = '[Prendre un rendez-vous en ligne](/rdv/create/)'
LIEN_MES_RDV = '[Consulter mes rendez-vous](/mes-rendez-vous/)'
LIEN_EXTRANET = '[Accéder à mon espace patient](/extranet/)'
LIEN_FILE = '[Voir ma position dans la file](/file-dattente/)'
LIEN_DECONNEXION = '[Me déconnecter](/logout/)'
LIEN_SERVICES = '[Découvrir nos soins et services](/)'


class ChatbotEngine:
    SALUTATIONS = [
        "Bonjour ! Je suis l'assistant virtuel du Centre Dentaire. Comment puis-je vous aider ?",
        "Bonjour et bienvenue ! Je suis là pour répondre à vos questions sur nos soins dentaires.",
    ]
    AU_REVOIR = [
        "Au revoir ! N'hésitez pas à revenir si vous avez d'autres questions.",
        "A bientot ! Prenez soin de vos dents.",
    ]
    INCOMPREHENSION = [
        "Je suis desole, je n'ai pas bien compris. Pourriez-vous reformuler ?",
        "Hmm, je ne suis pas sur de comprendre. Essayez avec : services, prix, urgence ou rendez-vous.",
    ]

    INTENTIONS = {
        'salutation': r'\b(bonjour|salut|bonsoir|coucou|hello|hi|hey|slt|cc|bjr|wesh|labas|salam|salem)\b',
        'au_revoir': r'\b(au revoir|bye|a bientot|a plus|merci au revoir)\b',
        'prise_rdv': r'\b(prendre rendez-vous|prendre un rdv|prendre rdv|rdv|rendez-vous|reservation|reserver)\b',
        'annulation_rdv': r'\b(annuler|supprimer|deplacer|modifier mon rdv|changer date)\b',
        'urgence': r'\b(urgence|urgent|douleur|mal aux dents|saignement|casse|dent cassee|abces|infection)\b',
        'services': r'\b(services|soins|traitement|consultation|detartrage|blanchiment|implant|orthodontie|carie|extraction)\b',
        'tarifs': r'\b(prix|tarif|cout|combien|cher|pas cher|remboursement|mutuelle|payer)\b',
        'horaires': r'\b(horaire|horaires|ouvert|ferme|quand|jours|heure|matin|apres-midi|dimanche|week-end)\b',
        'localisation': r'\b(adresse|localisation|comment venir|parking|acces|trouver)\b',
        'contact': r'\b(telephone|email|mail|joindre|appeler|contact|numero)\b',
        'preparation': r'\b(preparer|avant la consultation|a apporter|documents|carte vitale)\b',
        'post_soin': r'\b(apres-soin|douleur apres|manger apres|brosser|recommandation)\b',
        'file_attente': r'\b(file d\'attente|attendre|combien de temps|ma position|numero|ticket)\b',
        'compte': r'\b(mon compte|connexion|mot de passe|inscription|creer compte|extranet)\b',
        'remerciement': r'\b(merci beaucoup|thank you|thanks|super merci|genial merci|parfait merci)\b',
    }

    # Priorité en cas de chevauchement d'intentions (score = nb_match * priorité).
    INTENT_PRIORITY = {
        'urgence': 100,
        'annulation_rdv': 95,
        'tarifs': 90,
        'file_attente': 88,
        'prise_rdv': 85,
        'services': 80,
        'horaires': 75,
        'contact': 70,
        'localisation': 70,
        'preparation': 65,
        'post_soin': 65,
        'compte': 60,
        'au_revoir': 55,
        'salutation': 50,
        'remerciement': 40,
    }

    HORAIRES_CABINET = {
        0: ('8h00', '17h20'),
        1: ('8h00', '17h20'),
        2: ('8h00', '17h20'),
        3: ('8h00', '17h20'),
        4: ('8h00', '12h10'),
        5: ('Ferme', ''),
        6: ('Ferme', ''),
    }
    JOURS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    # Salutations exactes ou abréviations (darija / SMS / fautes courantes)
    SALUTATION_MOTS = frozenset({
        'salut', 'slt', 'sltt', 'ssalut', 'cc', 'coucou', 'bonjour', 'bjr', 'bonjours',
        'bonsoir', 'bsr', 'hello', 'hi', 'hey', 'yo', 're', 'wesh', 'labas', 'labes',
        'salam', 'salem', 'slm', 'sbah', 'bonjourr', 'salutt',
    })
    SALUTATION_REFERENCES = ('salut', 'bonjour', 'bonsoir', 'coucou', 'hello', 'salam', 'labas')

    def __init__(self, conversation=None):
        self.conversation = conversation
        self.contexte = conversation.contexte if conversation else {}
        self.historique = []
        if conversation:
            self._charger_historique()

    @staticmethod
    def normaliser_entree(texte):
        if not texte:
            return ''
        texte = str(texte).strip()
        if len(texte) > MAX_MESSAGE_LENGTH:
            texte = texte[:MAX_MESSAGE_LENGTH]
        texte = unicodedata.normalize('NFKD', texte)
        texte = ''.join(c for c in texte if not unicodedata.combining(c))
        return texte.lower().strip()

    @staticmethod
    def _relaxer_texte(texte):
        """Corrige fautes fréquentes : lettres doublées, ponctuation."""
        texte = re.sub(r'[^\w\s\']', ' ', texte)
        texte = re.sub(r'\s+', ' ', texte).strip()
        # ssalut → salut, bonjouur → bonjour
        texte = re.sub(r'(.)\1+', r'\1', texte)
        return texte

    def _detecter_salutation(self, texte_lower):
        """Salutations même avec fautes, abréviations ou message très court."""
        relaxed = self._relaxer_texte(texte_lower)
        candidats = {texte_lower, relaxed, texte_lower.strip('s')}

        for candidat in candidats:
            if not candidat:
                continue
            if candidat in self.SALUTATION_MOTS:
                return True
            for ref in self.SALUTATION_REFERENCES:
                if SequenceMatcher(None, candidat, ref).ratio() >= 0.78:
                    return True

        tokens = relaxed.split()
        if tokens and len(tokens) <= 4 and len(relaxed) <= 50:
            for token in tokens:
                if token in self.SALUTATION_MOTS:
                    return True
                for ref in self.SALUTATION_REFERENCES:
                    if SequenceMatcher(None, token, ref).ratio() >= 0.78:
                        return True
        return False

    def _charger_historique(self):
        messages = self.conversation.messages.order_by('-created_at')[:10]
        self.historique = [
            {'role': msg.role, 'content': msg.contenu}
            for msg in reversed(list(messages))
        ]

    def detecter_intention(self, texte):
        texte_lower = self.normaliser_entree(texte)
        if not texte_lower:
            return 'inconnu'

        if self._detecter_salutation(texte_lower):
            return 'salutation'

        variantes = [texte_lower, self._relaxer_texte(texte_lower)]
        scores = {}
        for variante in variantes:
            if not variante:
                continue
            for intention, pattern in self.INTENTIONS.items():
                matches = len(re.findall(pattern, variante, re.IGNORECASE))
                if matches > 0:
                    priorite = self.INTENT_PRIORITY.get(intention, 50)
                    score = matches * priorite
                    scores[intention] = max(scores.get(intention, 0), score)

        if not scores:
            return self._detecter_par_similarite(texte_lower)

        intention = max(scores, key=scores.get)
        logger.debug(
            'Intention detectee=%s scores=%s texte=%r',
            intention, scores, texte_lower[:80],
        )
        return intention

    def _detecter_par_similarite(self, texte):
        faqs = FAQDentaire.objects.filter(actif=True)
        meilleur_score = 0
        meilleure_categorie = 'inconnu'
        for faq in faqs:
            score_q = SequenceMatcher(None, texte.lower(), faq.question.lower()).ratio()
            score_k = 0
            if faq.mots_cles:
                mots = [m.strip().lower() for m in faq.mots_cles.split(',') if m.strip()]
                if mots:
                    score_k = sum(1 for m in mots if m in texte) / len(mots)
            score_total = score_q * 0.7 + score_k * 0.3
            if score_total > meilleur_score and score_total > 0.4:
                meilleur_score = score_total
                meilleure_categorie = faq.categorie
        mapping = {
            'services': 'services',
            'rdv': 'prise_rdv',
            'urgence': 'urgence',
            'tarifs': 'tarifs',
            'horaires': 'horaires',
            'preparation': 'preparation',
            'post_op': 'post_soin',
            'general': 'salutation',
        }
        return mapping.get(meilleure_categorie, 'inconnu')

    def rechercher_faq(self, texte, categorie=None, limite=3):
        mots = [m.lower() for m in re.findall(r'\b\w{3,}\b', texte)]
        queryset = FAQDentaire.objects.filter(actif=True)
        if categorie:
            queryset = queryset.filter(categorie=categorie)
        resultats = []
        for faq in queryset:
            score = 0
            score += SequenceMatcher(None, texte.lower(), faq.question.lower()).ratio() * 50
            if faq.mots_cles:
                mots_cles = [m.strip().lower() for m in faq.mots_cles.split(',') if m.strip()]
                score += sum(2 for m in mots if m in mots_cles)
            score += sum(1 for m in mots if m in faq.reponse.lower())
            if score > 5:
                resultats.append((score, faq))
        resultats.sort(key=lambda x: x[0], reverse=True)
        return [faq for _, faq in resultats[:limite]]

    def generer_reponse(self, texte, utilisateur=None):
        texte = self.normaliser_entree(texte) or texte
        intention = self.detecter_intention(texte)
        handlers = {
            'salutation': self._handle_salutation,
            'au_revoir': self._handle_au_revoir,
            'prise_rdv': self._handle_prise_rdv,
            'annulation_rdv': self._handle_annulation_rdv,
            'urgence': self._handle_urgence,
            'services': self._handle_services,
            'tarifs': self._handle_tarifs,
            'horaires': self._handle_horaires,
            'localisation': self._handle_localisation,
            'contact': self._handle_contact,
            'preparation': self._handle_preparation,
            'post_soin': self._handle_post_soin,
            'file_attente': self._handle_file_attente,
            'compte': self._handle_compte,
            'remerciement': self._handle_remerciement,
        }
        handler = handlers.get(intention, self._handle_inconnu)
        try:
            resultat = handler(texte, utilisateur)
        except Exception:
            logger.exception('Erreur handler chatbot intention=%s', intention)
            resultat = {
                'reponse': random.choice(self.INCOMPREHENSION),
                'suggestions': ['Voir les services', 'Horaires', 'Urgence'],
                'confiance': 0.2,
            }

        reponse = (resultat.get('reponse') or '').strip()
        if not reponse:
            logger.warning('Reponse vide pour intention=%s, fallback applique', intention)
            reponse = random.choice(self.INCOMPREHENSION)
            resultat['confiance'] = min(resultat.get('confiance', 0.5), 0.3)

        self._mettre_a_jour_contexte(intention, resultat)
        return {
            'reponse': reponse,
            'intention': intention,
            'action': resultat.get('action'),
            'suggestions': resultat.get('suggestions', []),
            'confiance': resultat.get('confiance', 0.8),
            'sources': resultat.get('sources', []),
        }

    def _mettre_a_jour_contexte(self, intention, resultat):
        if not self.conversation:
            return
        self.contexte['derniere_intention'] = intention
        self.contexte['dernier_sujet'] = resultat.get('sujet', intention)
        if intention == 'services' and 'service_id' in resultat:
            self.contexte['service_interesse'] = resultat['service_id']
        if intention == 'prise_rdv':
            self.contexte['en_discussion_rdv'] = True
        self.conversation.contexte = self.contexte
        self.conversation.sujet = self.contexte.get('dernier_sujet', '')
        self.conversation.save(update_fields=['contexte', 'sujet'])

    def _cabinet_ouvert_maintenant(self):
        now = timezone.localtime()
        jour = now.weekday()
        ouv, fer = self.HORAIRES_CABINET[jour]
        if ouv == 'Ferme':
            return False
        ouv_h = int(ouv.split('h')[0])
        fer_parts = fer.split('h')
        fer_h = int(fer_parts[0])
        fer_m = int(fer_parts[1]) if len(fer_parts) > 1 and fer_parts[1] else 0
        now_minutes = now.hour * 60 + now.minute
        return ouv_h * 60 <= now_minutes < fer_h * 60 + fer_m

    def _handle_salutation(self, texte, utilisateur):
        heure = timezone.localtime().hour
        salut = 'Bonjour !' if heure < 18 else 'Bonsoir !'
        return {
            'reponse': (
                f"{salut} Je suis l'assistant virtuel du Centre Dentaire. Je peux vous aider avec :\n\n"
                f"- Nos services (consultation, detartrage, implants...)\n"
                f"- Prendre un rendez-vous\n"
                f"- Horaires et acces\n"
                f"- Tarifs et remboursement\n"
                f"- Urgences dentaires\n\n"
                f"Que souhaitez-vous faire ?"
            ),
            'suggestions': ['Voir les services', 'Prendre un RDV', 'Horaires', 'Urgence'],
            'confiance': 0.95,
        }

    def _handle_au_revoir(self, texte, utilisateur):
        return {'reponse': random.choice(self.AU_REVOIR), 'suggestions': [], 'confiance': 0.95}

    def _handle_prise_rdv(self, texte, utilisateur):
        if not utilisateur or not utilisateur.is_authenticated:
            return {
                'reponse': (
                    "Pour prendre un rendez-vous, connectez-vous d'abord à votre compte patient.\n\n"
                    f"{LIEN_CONNEXION}\n\n"
                    "Les comptes sont créés par l'administration du cabinet "
                    "(pas d'inscription en ligne)."
                ),
                'action': 'redirect_login',
                'suggestions': ['Se connecter', 'Voir les services', 'Contact'],
                'confiance': 0.9,
            }
        creneaux = get_creneaux_disponibles()[:5]
        if not creneaux:
            return {
                'reponse': (
                    "Aucun créneau disponible pour le moment.\n\n"
                    f"{LIEN_RDV}\n"
                    "Ou contactez le cabinet par téléphone."
                ),
                'action': 'suggest_rdv',
                'suggestions': ['Voir le calendrier', 'Contact', 'Horaires'],
                'confiance': 0.75,
            }
        reponse = "Parfait ! Voici les prochains creneaux disponibles :\n\n"
        for i, (_, label) in enumerate(creneaux, 1):
            reponse += f"{i}. {label}\n"
        reponse += f"\n{LIEN_RDV}"
        return {
            'reponse': reponse,
            'action': 'suggest_rdv',
            'suggestions': ['Reserver maintenant', 'Voir tous les services', 'Tarifs'],
            'confiance': 0.85,
        }

    def _handle_annulation_rdv(self, texte, utilisateur):
        if not utilisateur or not utilisateur.is_authenticated:
            return {
                'reponse': f"Connectez-vous d'abord à votre compte.\n\n{LIEN_CONNEXION}",
                'action': 'redirect_login',
                'suggestions': ['Se connecter', 'Contacter le cabinet'],
                'confiance': 0.9,
            }
        rdvs = Rendez_vous.objects.filter(
            utilisateur=utilisateur,
            status__in=['pending', 'confirmed'],
            date__gte=timezone.now(),
        ).order_by('date')[:3]
        if not rdvs:
            return {
                'reponse': "Vous n'avez aucun rendez-vous a venir.",
                'suggestions': ['Prendre un RDV', 'Voir mes RDV'],
                'confiance': 0.9,
            }
        reponse = "Voici vos rendez-vous a venir :\n\n"
        for rdv in rdvs:
            date_fr = timezone.localtime(rdv.date).strftime('%d/%m/%Y a %H:%M')
            reponse += f"- {rdv.titre} — {date_fr}\n"
        reponse += f"\n{LIEN_MES_RDV}"
        return {
            'reponse': reponse,
            'action': 'redirect_mes_rdv',
            'suggestions': ['Gerer mes RDV', 'Prendre un nouveau RDV'],
            'confiance': 0.85,
        }

    def _handle_urgence(self, texte, utilisateur):
        patterns = {
            'douleur': r'\b(douleur|mal|souffrir|souffre|sensible)\b',
            'casse': r'\b(cassee?|brisee?|fracturee?|ebrechure?|couronne)\b',
            'saignement': r'\b(saigne|saignement|sang)\b',
            'abces': r'\b(abces|infection|gonfle|enfle|pus)\b',
            'arrachee': r'\b(arrachee?|dechaussee?|tomber|tombe)\b',
        }
        type_urgence = 'general'
        for typ, pattern in patterns.items():
            if re.search(pattern, texte, re.IGNORECASE):
                type_urgence = typ
                break
        conseils = {
            'douleur': "Prenez un anti-douleur (Paracetamol ou Ibuprofene) et evitez les aliments tres chauds ou tres froids.",
            'casse': "Conservez les fragments de dent dans du lait ou de la salive. Ne touchez pas a la racine.",
            'saignement': "Appliquez une compresse sterile et mordez fermement pendant 20 minutes.",
            'abces': "Ne mettez pas de chaleur sur la joue. Rincez-vous avec de l'eau salee tiede.",
            'arrachee': "Recuperez la dent par la couronne, rincez-la et essayez de la replacer. Sinon, conservez-la dans du lait.",
            'general': "Restez calme et evitez de manipuler la zone concernee.",
        }
        return {
            'reponse': (
                "URGENCE DENTAIRE\n\n"
                f"{conseils.get(type_urgence, conseils['general'])}\n\n"
                "Contactez-nous immediatement :\n"
                "Telephone : 05 22 XX XX XX\n"
                "Email : urgence@cabinet-dentaire.ma\n\n"
                f"Besoin urgent ? {LIEN_RDV}"
            ),
            'action': 'urgence_detectee',
            'suggestions': ['Appeler le cabinet', 'Prendre RDV urgent'],
            'confiance': 0.95,
            'sujet': 'urgence',
        }

    def _handle_services(self, texte, utilisateur):
        services = Service.objects.all()
        faqs = self.rechercher_faq(texte, categorie='services', limite=1)
        if faqs:
            faq = faqs[0]
            faq.incrementer_usage()
            return {
                'reponse': (
                    f"{faq.question}\n\n{faq.reponse}\n\n"
                    f"{LIEN_SERVICES}\n"
                    f"{LIEN_RDV}"
                ),
                'suggestions': ['Prendre un RDV', 'Tarifs', 'Horaires'],
                'confiance': 0.9,
                'sources': [faq.question],
            }
        reponse = "Nos services dentaires\n\n"
        for svc in services[:6]:
            duree = getattr(svc, 'duree_minutes', 30)
            reponse += f"- {svc.nom} — {duree} min\n"
        if not services.exists():
            reponse += "- Consultation generale\n- Detartrage\n- Soins conservateurs\n"
        reponse += f"\n{LIEN_SERVICES}\n"
        reponse += LIEN_RDV
        return {
            'reponse': reponse,
            'suggestions': ['Consultation', 'Detartrage', 'Implants', 'Prendre un RDV'],
            'confiance': 0.85,
        }

    def _handle_tarifs(self, texte, utilisateur):
        faqs = self.rechercher_faq(texte, categorie='tarifs', limite=2)
        reponse = "Tarifs et remboursement\n\n"
        if faqs:
            for faq in faqs:
                faq.incrementer_usage()
                reponse += f"{faq.question}\n{faq.reponse}\n\n"
        else:
            reponse += (
                "Nos tarifs sont conformes a la convention dentaire.\n\n"
                "Exemples indicatifs :\n"
                "- Consultation : 25€ – 40€\n"
                "- Detartrage : 30€ – 50€\n"
                "- Carie simple : 40€ – 80€\n\n"
            )
        reponse += LIEN_RDV
        return {
            'reponse': reponse,
            'suggestions': ['Prendre un RDV', 'Voir les services', 'Horaires'],
            'confiance': 0.8,
            'sources': [f.question for f in faqs],
        }

    def _handle_horaires(self, texte, utilisateur):
        reponse = "Horaires d'ouverture\n\n"
        for i, (ouv, fer) in self.HORAIRES_CABINET.items():
            if ouv == 'Ferme':
                reponse += f"- {self.JOURS[i]} : Ferme\n"
            else:
                reponse += f"- {self.JOURS[i]} : {ouv} – {fer}\n"
        if self._cabinet_ouvert_maintenant():
            reponse += "\nNous sommes ouverts en ce moment !"
        else:
            reponse += "\nNous sommes actuellement fermes."
        reponse += f"\n\n{LIEN_RDV}"
        return {
            'reponse': reponse,
            'suggestions': ['Prendre un RDV', 'Urgence', 'Services'],
            'confiance': 0.9,
        }

    def _handle_localisation(self, texte, utilisateur):
        return {
            'reponse': (
                "Ou nous trouver\n\n"
                "Centre Dentaire\n"
                "123 Avenue Mohammed V\n"
                "20000 Casablanca, Maroc\n\n"
                "Parking : Parking public a 50m\n"
                "Transport : Arret bus Ligne 15 a 100m\n\n"
                "Voir sur Google Maps : https://maps.google.com/?q=Centre+Dentaire+Casablanca"
            ),
            'suggestions': ['Horaires', 'Prendre un RDV', 'Contact'],
            'confiance': 0.95,
        }

    def _handle_contact(self, texte, utilisateur):
        return {
            'reponse': (
                "Contactez-nous\n\n"
                "Telephone : 05 22 XX XX XX\n"
                "Email : contact@cabinet-dentaire.ma\n"
                "WhatsApp : 06 XX XX XX XX\n\n"
                f"{LIEN_RDV}\n"
                f"{LIEN_CONNEXION}"
            ),
            'suggestions': ['Prendre un RDV', 'Urgence', 'Horaires'],
            'confiance': 0.95,
        }

    def _handle_preparation(self, texte, utilisateur):
        faqs = self.rechercher_faq(texte, categorie='preparation', limite=2)
        reponse = "Preparer votre visite\n\n"
        if faqs:
            for faq in faqs:
                faq.incrementer_usage()
                reponse += f"{faq.question}\n{faq.reponse}\n\n"
        else:
            reponse += (
                "Pour votre premiere consultation, apportez :\n\n"
                "- Carte d'identite\n"
                "- Carte de mutuelle\n"
                "- Derniers radios dentaires\n"
                "- Liste de vos medicaments\n\n"
                "Arrivez 10 minutes avant votre rendez-vous."
            )
        return {
            'reponse': reponse,
            'suggestions': ['Prendre un RDV', 'Tarifs', 'Horaires'],
            'confiance': 0.85,
        }

    def _handle_post_soin(self, texte, utilisateur):
        faqs = self.rechercher_faq(texte, categorie='post_op', limite=2)
        reponse = "Apres votre soin\n\n"
        if faqs:
            for faq in faqs:
                faq.incrementer_usage()
                reponse += f"{faq.question}\n{faq.reponse}\n\n"
        else:
            reponse += (
                "Conseils generaux apres un soin dentaire :\n\n"
                "- Evitez de manger pendant 2h apres une anesthesie\n"
                "- Pas d'aliments durs ou collants le jour meme\n"
                "- Brossez-vous les dents doucement\n"
                "- En cas de douleur persistante > 48h, contactez-nous\n\n"
                "Urgence : 05 22 XX XX XX"
            )
        return {
            'reponse': reponse,
            'suggestions': ['Urgence', 'Prendre un RDV', 'Contact'],
            'confiance': 0.8,
        }

    def _handle_file_attente(self, texte, utilisateur):
        reponse = "File d'attente\n\n"
        if utilisateur and utilisateur.is_authenticated:
            from .views import _patient_queue_day, _pending_queue_for_day
            queue_day = _patient_queue_day(utilisateur)
            if not queue_day:
                reponse += "Vous n'avez pas de rendez-vous en attente.\n\n"
                reponse += LIEN_FILE
                return {
                    'reponse': reponse,
                    'suggestions': ['Prendre un RDV', 'Mes RDV'],
                    'confiance': 0.85,
                }
            start_day, end_day = cabinet_day_datetime_bounds(queue_day)
            rdv_called = Rendez_vous.objects.filter(
                utilisateur=utilisateur,
                status='confirmed',
                date__gte=start_day,
                date__lt=end_day,
            ).order_by('date').first()
            if rdv_called:
                reponse += (
                    "Vous etes appele(e) ! Presentez-vous au cabinet.\n\n"
                )
            rdv_user = Rendez_vous.objects.filter(
                utilisateur=utilisateur,
                status='pending',
                date__gte=start_day,
                date__lt=end_day,
            ).order_by('date').first()
            if rdv_user:
                position = self._calculer_position(rdv_user)
                ahead = position - 1 if position else 0
                if position:
                    reponse += f"File du {queue_day:%d/%m/%Y}\n"
                    reponse += f"Votre position : #{position}\n"
                    if ahead:
                        reponse += f"Patients devant vous : {ahead}\n"
                    reponse += "\n"
            elif not rdv_called:
                reponse += f"File du {queue_day:%d/%m/%Y} — rendez-vous prevu ce jour.\n\n"
            reponse += LIEN_FILE
        else:
            reponse += (
                "Connectez-vous pour voir votre position dans la file.\n\n"
                f"{LIEN_CONNEXION}"
            )
        return {
            'reponse': reponse,
            'action': 'redirect_login' if not (utilisateur and utilisateur.is_authenticated) else None,
            'suggestions': ['Se connecter', 'Prendre un RDV', 'Mes RDV'],
            'confiance': 0.85,
        }

    def _handle_compte(self, texte, utilisateur):
        if utilisateur and utilisateur.is_authenticated:
            return {
                'reponse': (
                    f"Votre compte\n\n"
                    f"Connecte : {utilisateur.email or utilisateur.username}\n\n"
                    f"{LIEN_EXTRANET}\n"
                    f"{LIEN_MES_RDV}\n"
                    f"{LIEN_RDV}\n"
                    f"{LIEN_DECONNEXION}"
                ),
                'suggestions': ['Mes RDV', 'Prendre un RDV'],
                'confiance': 0.9,
            }
        return {
            'reponse': (
                "Espace patient\n\n"
                "Connectez-vous pour :\n"
                "- Prendre et gerer vos rendez-vous\n"
                "- Voir votre historique\n"
                "- Consulter votre file d'attente\n\n"
                f"{LIEN_CONNEXION}\n\n"
                "Pas d'inscription publique : demandez un accès au cabinet."
            ),
            'action': 'redirect_login',
            'suggestions': ['Se connecter', 'Contact'],
            'confiance': 0.9,
        }

    def _handle_remerciement(self, texte, utilisateur):
        return {
            'reponse': "Je vous en prie ! N'hesitez pas si vous avez d'autres questions.",
            'suggestions': ['Prendre un RDV', 'Services', 'Au revoir'],
            'confiance': 0.9,
        }

    def _handle_inconnu(self, texte, utilisateur):
        faqs = self.rechercher_faq(texte, limite=1)
        if faqs:
            faq = faqs[0]
            faq.incrementer_usage()
            return {
                'reponse': f"{faq.reponse}\n\nCela repond-il a votre question ?",
                'suggestions': ['Oui, merci', 'Non, autre question', 'Parler a un agent'],
                'confiance': 0.6,
                'sources': [faq.question],
            }
        return {
            'reponse': random.choice(self.INCOMPREHENSION),
            'suggestions': ['Voir les services', 'Horaires', 'Urgence', 'Parler a un agent'],
            'confiance': 0.3,
        }

    def _queue_ordered(self):
        qs = Rendez_vous.objects.filter(status='pending')
        return sorted(qs, key=lambda r: (0 if r.priority == 'urgent' else 1, r.date, r.created_at))

    def _calculer_position(self, rdv):
        from .views import _pending_queue_for_day
        day = rdv_datetime_cabinet(rdv).date()
        for i, item in enumerate(_pending_queue_for_day(day), 1):
            if item.pk == rdv.pk:
                return i
        return None
