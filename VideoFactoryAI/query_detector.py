# query_detector.py

import re


class SearchQueryDetector:

    EVENTS = {
        "dartmouth": "Dartmouth Conference 1956",
        "deep blue": "Deep Blue chess computer",
        "alexnet": "AlexNet neural network",
        "logic theorist": "Logic Theorist AI program",
        "enigma": "Enigma machine",
        "segunda guerra mundial": "World War II codebreaking",
        "criptoanálise": "Bletchley Park codebreaking",
    }

    TOPICS = {
        "rede neural": "early neural network diagram",
        "redes neurais": "early neural network diagram",
        "neurônio artificial": "artificial neuron diagram",
        "processamento": "mainframe computer room",
        "memória": "early computer memory",
        "computador eletrônico": "early computer laboratory",
        "autômato": "ancient automaton machine",
        "autômatos": "ancient automaton machine",
    }

    BLACKLIST = {
        "Inteligência Artificial",
        "Segunda Guerra Mundial",
        "Primeira Guerra Mundial",
    }

    PERSON_PATTERN = re.compile(
        r'\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]'
        r'[a-záàâãéêíóôõúç]+'
        r'(?:\s+(?:de|da|do|dos|das|von|van|del))?'
        r'(?:\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]'
        r'[a-záàâãéêíóôõúç]+){1,3}'
        r'\b'
    )

    def extract_person(self, text):

        matches = self.PERSON_PATTERN.findall(text)

        for candidate in matches:

            if candidate in self.BLACKLIST:
                continue

            return candidate

        return None

    def detect_event(self, text):

        lower = text.lower()

        for key, value in self.EVENTS.items():

            if key in lower:
                return value

        return None

    def detect_topic(self, text):

        lower = text.lower()

        for key, value in self.TOPICS.items():

            if key in lower:
                return value

        return None

    def fallback(self, text):

        words = re.findall(
            r'\b[a-zA-ZÀ-ÿ]{5,}\b',
            text
        )

        stopwords = {
            "durante",
            "entretanto",
            "tambem",
            "também",
            "ainda",
            "porque",
            "quando",
            "onde",
            "inteligência",
            "artificial",
            "computadores",
        }

        words = [
            w
            for w in words
            if w.lower() not in stopwords
        ]

        return " ".join(words[:4])

    def build(self, text):

        person = self.extract_person(text)

        if person:
            return f"{person} portrait"

        event = self.detect_event(text)

        if event:
            return event

        topic = self.detect_topic(text)

        if topic:
            return topic

        return self.fallback(text)