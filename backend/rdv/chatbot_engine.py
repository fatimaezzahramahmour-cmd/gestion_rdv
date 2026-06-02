import re
import random
from datetime import timedelta
from difflib import SequenceMatcher
from django.utils import timezone

from .models import Conversation, MessageChatbot, FAQDentaire, Rendez_vous, Service


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
        "Hmm, je ne suis pas sur de comprendre. Essayez avec : consultation, prix, urgence ou rendez-vous.",
    ]

    INTENTIONS = {
        'salutation': r'\b(bonjour|salut|bonsoir|coucou|hello|hi|hey)\b',
        'au_revoir': r'\b(au revoir|bye|a bientot|a plus|merci au revoir)\b',
        'prise_rdv': r'\b(prendre rendez-vous|prendre un rdv|rdv|rendez-vous|reservation|reserver|consultation)\b',
        'annulation_rdv': r'\b(annuler|supprimer|deplacer|modifier mon rdv|changer date)\b',
        'urgence': r'\b(urgence|urgent|douleur|mal|saignement|casse|dent cassee|abces|infection)\b',
        'services': r'\b(services|soins|traitement|detartrage|blanchiment|implant|orthodontie|carie|extraction)\b',
        'tarifs': r'\b(prix|tarif|cout|combien|cher|pas cher|remboursement|mutuelle|payer)\b',
        'horaires': r'\b(horaire|ouvert|ferme|quand|jours|heure|matin|apres-midi|dimanche|week-end)\b',
        'localisation': r'\b(ou|adresse|localisation|comment venir|parking|acces|trouver)\b',
        'contact': r'\b(telephone|email|mail|joindre|appeler|contact|numero)\b',
        'preparation': r'\b(preparer|avant|avant la consultation|a apporter|documents|carte vitale)\b',
        'post_soin': r'\b(apres|apres-soin|douleur apres|manger|brosser|suivre|recommandation)\b',
        'file_attente': r'\b(file d\'attente|attendre|combien de temps|position|numero|ticket)\b',
        'compte': r'\b(mon compte|connexion|mot de passe|inscription|creer compte|extranet)\b',
        'remerciement': r'\b(merci|thank|thanks|super|genial|parfait|ok|d\'accord)\b',
    }

    def __init__(self, conversation=None):
        self.conversation = conversation
        self.contexte = conversation.contexte if conversation else {}
        self.historique = []
        if conversation:
            self._charger_historique()

    def _charger_historique(self):
        messages = self.conversation.messages.order_by('-created_at')[:10]
        self.historique = [
            {"role": msg.role, "content": msg.contenu}
            for msg in reversed(list(messages))
        ]

    def detecter_intention(self, texte):
        texte_lower = texte.lower().strip()
        scores = {}
        for intention, pattern in self.INTENTIONS.items():
            matches = len(re.findall(pattern, texte_lower, re.IGNORECASE))
            if matches > 0:
                scores[intention] = matches
        if not scores:
            return self._detecter_par_similarite(texte_lower)
        return max(scores, key=scores.get)

    def _detecter_par_similarite(self, texte):
        faqs = FAQDentaire.objects.filter(actif=True)
        meilleur_score = 0
        meilleure_categorie = 'inconnu'
        for faq in faqs:
            score_q = SequenceMatcher(None, texte.lower(), faq.question.lower()).ratio()
            score_k = 0
            if faq.mots_cles:
                mots = [m.strip().lower() for m in faq.mots_cles.split(',')]
                score_k = sum(1 for m in mots if m in texte) / len(mots)
            score_total = score_q * 0.7 + score_k * 0.3
            if score_total > meilleur_score and score_total > 0.4:
                meilleur_score = score_total
                meilleure_categorie = faq.categorie
        mapping = {
            'services': 'services', 'rdv': 'prise_rdv', 'urgence': 'urgence',
            'tarifs': 'tarifs', 'horaires': 'horaires', 'preparation': 'preparation',
            'post_op': 'post_soin', 'general': 'salutation',
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
                mots_cles = [m.strip().lower() for m in faq.mots_cles.split(',')]
                score += sum(2 for m in mots if m in mots_cles)
            score += sum(1 for m in mots if m in faq.reponse.lower())
            if score > 5:
                resultats.append((score, faq))
        resultats.sort(key=lambda x: x[0], reverse=True)
        return [faq for _, faq in resultats[:limite]]

    def generer_reponse(self, texte, utilisateur=None):
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
        resultat = handler(texte, utilisateur)
        self._mettre_a_jour_contexte(intention, resultat)
        return {
            'reponse': resultat.get('reponse', ''),
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

    def _handle_salutation(self, texte, utilisateur):
        heure = timezone.localtime().hour
        salut = "Bonjour !" if heure < 18 else "Bonsoir !"
        return {
            'reponse': f"{salut} Je suis l'assistant virtuel du Centre Dentaire. Je peux vous aider avec :\n\n"
                       f"Nos services (consultation, detartrage, implants...)\n"
                       f"Prendre un rendez-vous\n"
                       f"Horaires et acces\n"
                       f"Tarifs et remboursement\n"
                       f"Urgences dentaires\n\n"
                       f"Que souhaitez-vous faire ?",
            'suggestions': ['Voir les services', 'Prendre un RDV', 'Horaires', 'Urgence'],
            'confiance': 0.95,
        }

    def _handle_au_revoir(self, texte, utilisateur):
        return {'reponse': random.choice(self.AU_REVOIR), 'suggestions': [], 'confiance': 0.95}

    def _handle_prise_rdv(self, texte, utilisateur):
        if not utilisateur or not utilisateur.is_authenticated:
            return {
                'reponse': "Pour prendre un rendez-vous, connectez-vous a votre compte patient.\n\n"
                           "Se connecter : /login/\n\n"
                           "Les comptes sont crees par l'administration du cabinet (pas d'inscription en ligne).",
                'action': 'redirect_login',
                'suggestions': ['Se connecter', 'Voir les services', 'Contact'],
                'confiance': 0.9,
            }
        creneaux = self._get_prochains_creneaux()
        reponse = "Parfait ! Voici les prochains creneaux disponibles :\n\n"
        for i, (date_str, heure) in enumerate(creneaux[:5], 1):
            reponse += f"{i}. {date_str} a {heure}\n"
        reponse += "\nReserver mon creneau : /rdv/create/\n"
        return {
            'reponse': reponse,
            'action': 'suggest_rdv',
            'suggestions': ['Reserver maintenant', 'Voir tous les services', 'Tarifs'],
            'confiance': 0.85,
        }

    def _handle_annulation_rdv(self, texte, utilisateur):
        if not utilisateur or not utilisateur.is_authenticated:
            return {
                'reponse': "Connectez-vous d'abord a votre compte.\n\nSe connecter : /login/",
                'action': 'redirect_login',
                'suggestions': ['Se connecter', 'Contacter le cabinet'],
                'confiance': 0.9,
            }
        rdvs = Rendez_vous.objects.filter(
            utilisateur=utilisateur, status__in=['pending', 'confirmed'],
            date__gte=timezone.now()
        ).order_by('date')[:3]
        if not rdvs:
            return {
                'reponse': "Vous n'avez aucun rendez-vous a venir.",
                'suggestions': ['Prendre un RDV', 'Voir mes RDV'],
                'confiance': 0.9,
            }
        reponse = "Voici vos rendez-vous a venir :\n\n"
        for rdv in rdvs:
            date_fr = rdv.date.strftime('%d/%m/%Y a %H:%M')
            reponse += f"- {rdv.titre} — {date_fr}\n"
        reponse += "\nGerer mes rendez-vous : /mes-rendez-vous/"
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
                "Prendre un RDV urgent : /rdv/create/?urgent=1"
            ),
            'action': 'urgence_detectee',
            'suggestions': ['Appeler le cabinet', 'Prendre RDV urgent'],
            'confiance': 0.95,
            'sujet': 'urgence',
        }

    def _handle_services(self, texte, utilisateur):
        services = Service.objects.all()
        service_keywords = {
            'consultation': 'consultation', 'detartrage': 'detartrage',
            'blanchiment': 'blanchiment', 'implant': 'implant',
            'orthodontie': 'orthodontie', 'carie': 'carie',
            'extraction': 'extraction', 'couronne': 'couronne',
        }
        service_demande = None
        for mot, slug in service_keywords.items():
            if mot in texte.lower():
                service_demande = slug
                break
        if service_demande:
            faqs = self.rechercher_faq(texte, categorie='services', limite=2)
            if faqs:
                faq = faqs[0]
                faq.incrementer_usage()
                return {
                    'reponse': f"{faq.question}\n\n{faq.reponse}\n\n"
                               f"Voir tous nos services : /soins-et-services/\n"
                               f"Prendre un RDV : /rdv/create/",
                    'suggestions': ['Prendre un RDV', 'Tarifs', 'Horaires'],
                    'confiance': 0.9,
                    'sources': [faq.question],
                }
        reponse = "Nos services dentaires\n\n"
        for svc in services[:6]:
            reponse += f"- {svc.nom} — {svc.duree_minutes} min\n"
        reponse += "\nDecouvrir tous nos services : /soins-et-services/\n"
        reponse += "Prendre un rendez-vous : /rdv/create/"
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
        reponse += "Demander un devis : /contact/"
        return {
            'reponse': reponse,
            'suggestions': ['Prendre un RDV', 'Voir les services', 'Horaires'],
            'confiance': 0.8,
            'sources': [f.question for f in faqs],
        }

    def _handle_horaires(self, texte, utilisateur):
        now = timezone.localtime()
        jour_semaine = now.weekday()
        heure = now.hour
        horaires = {
            0: ("8h30", "18h30"), 1: ("8h30", "18h30"), 2: ("8h30", "18h30"),
            3: ("8h30", "18h30"), 4: ("8h30", "12h30"), 5: ("Ferme", ""), 6: ("Ferme", ""),
        }
        jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
        reponse = "Horaires d'ouverture\n\n"
        for i, (ouv, fer) in horaires.items():
            if ouv == "Ferme":
                reponse += f"- {jours[i]} : Ferme\n"
            else:
                reponse += f"- {jours[i]} : {ouv} – {fer}\n"
        if jour_semaine < 4:
            ouv_h = int(horaires[jour_semaine][0].split('h')[0])
            fer_h = int(horaires[jour_semaine][1].split('h')[0])
            if ouv_h <= heure < fer_h:
                reponse += "\nNous sommes ouverts en ce moment !"
            else:
                reponse += "\nNous sommes actuellement fermes."
        else:
            reponse += "\nNous sommes actuellement fermes."
        reponse += "\n\nPrendre un rendez-vous : /rdv/create/"
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
                "Formulaire de contact : /contact/\n"
                "Prendre un RDV : /rdv/create/"
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
                "- Carte Vitale\n"
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
        en_attente = Rendez_vous.objects.filter(status='pending').count()
        urgents = Rendez_vous.objects.filter(status='pending', priority='urgent').count()
        reponse = (
            "File d'attente actuelle\n\n"
            f"- {en_attente} patient(s) en attente\n"
            f"- {urgents} cas urgent(s) prioritaires\n\n"
        )
        if utilisateur and utilisateur.is_authenticated:
            rdv_user = Rendez_vous.objects.filter(
                utilisateur=utilisateur, status='pending'
            ).order_by('date').first()
            if rdv_user:
                position = self._calculer_position(rdv_user)
                reponse += f"Votre position : #{position}\n\n"
        reponse += "Voir la file complete : /file-dattente/"
        return {
            'reponse': reponse,
            'suggestions': ['Prendre un RDV', 'Mes RDV', 'Urgence'],
            'confiance': 0.85,
        }

    def _handle_compte(self, texte, utilisateur):
        if utilisateur and utilisateur.is_authenticated:
            return {
                'reponse': (
                    f"Votre compte\n\n"
                    f"Connecte : {utilisateur.email}\n\n"
                    f"Mon espace : /extranet/\n"
                    f"Mes RDV : /mes-rendez-vous/\n"
                    f"Prendre un RDV : /rdv/create/\n"
                    f"Deconnexion : /logout/"
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
                "Se connecter : /login/\n\n"
                "Pas d'inscription publique : demandez un acces au cabinet."
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

    def _get_prochains_creneaux(self):
        now = timezone.localtime()
        resultats = []
        for i in range(1, 8):
            date = now + timedelta(days=i)
            if date.weekday() < 5:
                nom_jour = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'][date.weekday()]
                resultats.append((f"{nom_jour} {date.day}/{date.month}", "09:00"))
                if date.weekday() < 4:
                    resultats.append((f"{nom_jour} {date.day}/{date.month}", "14:00"))
            if len(resultats) >= 5:
                break
        return resultats

    def _calculer_position(self, rdv):
        position = Rendez_vous.objects.filter(
            status='pending', priority='urgent', created_at__lt=rdv.created_at
        ).count()
        if rdv.priority != 'urgent':
            position += Rendez_vous.objects.filter(status='pending', priority='urgent').count()
            position += Rendez_vous.objects.filter(
                status='pending', priority__in=['normal', 'control'], created_at__lt=rdv.created_at
            ).count()
        return position + 1