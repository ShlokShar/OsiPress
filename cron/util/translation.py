
from deep_translator import GoogleTranslator

def translate(text: str) -> str:
    """

    :param text: the text to translate
    :return: the translated text in English
    """

    return GoogleTranslator(source="auto", target="en").translate(text)


def translate_references(references: list) -> list:
    """

    :param references: the list of quotes from the article in its original
    language
    :return: a list of the original quotes in English
    """

    return [translate(reference) for reference in references]
