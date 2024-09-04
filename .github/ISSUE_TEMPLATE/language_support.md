name: Language Support Request
description: Request support for a new language in this project
title: '[Language]: Add support for [my language]'
labels:
  - language
  - enhancement
body:
  - type: dropdown
    id: language
    attributes:
      label: Home Assistant Language
      description: Language of your HA instance, set in Settings => System => General
      options:
        - Afrikaans
        - العربية
        - Български
        - বাংলা
        - Català
        - Čeština
        - Dansk
        - Deutsch
        - Schwyzerdütsch
        - Ελληνικά
        - English
        - Español
        - Eesti
        - Euskara
        - فارسی
        - Suomi
        - Français
        - Français (Canada)
        - Galician
        - Gujarati
        - עברית
        - हिन्दी
        - Hrvatski
        - Magyar
        - Bahasa Indonesia
        - íslenska
        - Italiano
        - ქართული
        - ಕನ್ನಡ
        - 한국어
        - Lëtzebuergesch
        - Lietuvių
        - Latviešu
        - മലയാളം
        - монгол хэл
        - Bahasa Melayu
        - Norsk Bokmål
        - Nederlands
        - Polski
        - Português
        - Português (Brasil)
        - Română
        - Русский
        - Slovenčina
        - Slovenščina
        - Српски
        - Svenska
        - Kiswahili
        - తెలుగు
        - Türkçe
        - Українська
        - اُردُو
        - Tiếng Việt
        - 简体中文
        - 繁體中文（香港）
        - 繁體中文（台灣
    validations:
      required: true
  - type: input
    id: entity_id
    attributes:
      label: Entity ID
      description: ' You can find the entity ID by going to `Developer Tools` => `States` and searching for `todo`'
      placeholder: todo.einkaufsliste
    validations:
      required: true
