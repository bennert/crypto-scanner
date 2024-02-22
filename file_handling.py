"""File handling for json files"""

import json
import os

FILENAMEBUYSIGNALSACTIVE = "./state/buysignalsactive.json"
FILENAMEMINQUOTEVOLUME = "./state/minquotevol.json"
FILENAMEBASECOIN = "./state/basecoin.json"
FILENAMEPAIRLIST = "./state/pairlist.json"
FILENAMEMINSTOCHRSI = "./state/minstochrsi.json"
FILENAMEINDICATORTRIGGER = "./state/indicator_trigger.json"

def add_json(file_name, chat_id, value):
    """Add json value of chat_id to file"""
    json_dict = load_json(file_name)
    json_dict[chat_id] += value
    save_json(file_name, json_dict)

def update_json(file_name, chat_id, value):
    """Update json value of chat_id in file"""
    json_dict = load_json(file_name)
    json_dict[chat_id] = value
    save_json(file_name, json_dict)

def load_json(file_name):
    """Load json value of file"""
    value = {}
    if os.path.isfile(file_name):
        with open(file_name, 'r', encoding="utf-8") as file:
            value = json.load(file)
    return value

def save_json(file_name, json_value):
    """Save json string to file"""
    with open(file_name, 'w', encoding="utf-8") as file:
        json.dump(json_value, file)

def file_exists(file_name):
    """Check if file exists"""
    return os.path.isfile(file_name)
