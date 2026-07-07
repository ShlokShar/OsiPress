
from deep_translator import GoogleTranslator

def translate(text):
    return GoogleTranslator(source="auto", target="en").translate(text)