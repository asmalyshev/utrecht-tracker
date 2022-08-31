import json
import requests
import logging
import telegram
import telegram.ext
import pytz
from datetime import datetime
from typing import Dict, Any
from deepdiff import DeepDiff

JSON_FILE = 'json_data.json'
CONFIG_FILE = 'config.json'

logger = logging.getLogger(__name__)

def read_config() -> Dict[str, Any]:
    logger.debug('reading configuration')
    with open(CONFIG_FILE, 'r') as f:
        data = json.loads(f.read())
        logger.debug('config: %s', data)
        return data
        
def require_config_key(config: Dict[str, Any], config_key: str) -> Any:
    if config_key not in config:
        raise RuntimeError('"%s" config key expected')
    return config[config_key]

def todayAt (hr, min=0, sec=0, micros=0):
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    return now.replace(hour=hr, minute=min, second=sec, microsecond=micros)    

def main():
    try:
        # load configuration
        config = read_config()
        telegram_chat_id = require_config_key(config, 'telegram_chat_id')
        telegram_bot_token = require_config_key(config, 'telegram_bot_api_token')
        telegram_status_message_id = require_config_key(config, 'telegram_status_message_id')
        gemeente_request_url = require_config_key(config, 'gemeente_request_url')
        gemeente_reservation_url = require_config_key(config, 'gemeente_reservation_url')

        # load previous state
        with open(JSON_FILE) as json_file:
            data_storage = json.load(json_file)
        
        # get available dates
        response = requests.get(gemeente_request_url)
        json_data = json.loads(response.text)
        
        # store checktime
        tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(tz).replace(second=0, microsecond=0)
        now_string = now.strftime('%H:%M on %b %d')
        same_check_time = (now_string == data_storage['check_timestamp'])
        print_slots = (todayAt (9) == now)
        data_storage['check_timestamp'] = now_string
        
        # compare and find the difference
        compare = DeepDiff(data_storage['all_dates'], json_data, ignore_order=True)
        data_storage['added'] = []
        data_storage['removed'] = []
        if 'iterable_item_added' in compare:
            for item in compare['iterable_item_added']:
                data_storage['added'].append(compare['iterable_item_added'][item]["date"])
        if 'iterable_item_removed' in compare:
            for item in compare['iterable_item_removed']:
                data_storage['removed'].append(compare['iterable_item_removed'][item]["date"])
        if 'values_changed' in compare:
            for item in compare['values_changed']:
                data_storage['added'].append(compare['values_changed'][item]["new_value"])
                data_storage['removed'].append(compare['values_changed'][item]["old_value"])
        data_storage['all_dates'] = json_data
        
        # send notifications
        notification_text = ''
        if len(data_storage['added']) != 0 or len(data_storage['removed']) != 0:
            url = ''
            if len(data_storage['added']) != 0:
                notification_text = '🔥 Found new available days!\n'
                url = '\n\n{}'.format(gemeente_reservation_url)
            else:
                notification_text = '⚡️ Available days changed!\n'
            for date_added in data_storage['added']:
                notification_text += '\n' + '🟢 {}'.format(date_added)
            for date_removed in data_storage['removed']:
                notification_text += '\n' + '❌ {}'.format(date_removed)
            notification_text += url
        
        # print all available slots every 9AM
        if print_slots:
            notification_text += '\n\n Goedemorgen! 🇳🇱\nAll available dates:\n'
            for item in data_storage['all_dates']:
                notification_text += '\n' + '🟢 {}'.format(item["date"])
        
        bot = telegram.ext.ExtBot(telegram_bot_token, defaults=telegram.ext.Defaults(
            timeout=10,
        ))
        
        if notification_text != '':
            bot.send_message(
                chat_id=telegram_chat_id,
                text=notification_text
            )
        
        # update check time message
        if not same_check_time:
            status = '⚡ Last checked at %s (Moscow time)' % data_storage['check_timestamp']
            bot.edit_message_text(chat_id=telegram_chat_id, message_id=telegram_status_message_id, text=status)

        # store results
        with open(JSON_FILE, 'w') as outfile:
            json.dump(data_storage, outfile)
            
    except Exception as e:
        logger.exception('An error occurred: {}'.format(e))

# just calls the `main` function above
if __name__ == '__main__':
    logging.basicConfig(
        filename='bot.log',
        format='%(asctime)s %(levelname)s:%(message)s',
        level=logging.WARNING)
    main()