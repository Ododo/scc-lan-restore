import locale
import logging

def get_system_language():
    lang, _ = locale.getdefaultlocale()
    if lang.startswith('zh'):
        return 'zh'
    else:
        return 'en'

logging.basicConfig(format='%(message)s')
logger_zh = logging.getLogger('zh')
logger_en = logging.getLogger('en')

# control logger visibility based on system language (default log level is WARNING)
if get_system_language() == 'zh':
    logger_zh.setLevel(logging.INFO)
else:
    logger_en.setLevel(logging.INFO)
