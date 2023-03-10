import re
import requests
import unicodedata

from flask import Flask, render_template, request

app = Flask(__name__)

basic_names = [
    'mountain',
    'island',
    'swamp',
    'plains',
    'forest'
]

tiers = [
    ('Uber', 'uber', 30),
    ('Over Used', 'ou', 20),
    ('Under Used', 'uu', 10),
    ('Rarely Used', 'ru', 5),
    ('Never Used', 'nu', 2),
    ('PU', 'pu', 0),
]


def strip_accents(text):
    text = unicodedata.normalize('NFD', text)\
           .encode('ascii', 'ignore')\
           .decode("utf-8")

    return str(text)

def parse_int(string, default):
    if string:
        return int(string)
    return default


def fetch_edhrec_data(card_name: str):
    original_card_name = card_name

    try:
        card_name = card_name.lower()
        card_name = strip_accents(card_name)
        card_name = card_name.replace(',', "")
        card_name = card_name.replace("+", "plus ")
        card_name = card_name.replace("'", "")
        card_names = card_name.split("// ")
        card_name = card_names[0].strip()
        card_name = card_name.replace(" ", "-")

        try:
            url = f'https://json.edhrec.com/pages/cards/{card_name}.json'
            response = requests.get(url).json()
            print(url)
        except Exception as e:
            print(card_names)
            card_name = card_names[0].strip().replace(" ", "-") + "-" + card_names[1].strip().replace(" ", "-")
            url = f'https://json.edhrec.com/pages/cards/{card_name}.json'
            response = requests.get(url).json()

        edhrec_pattern = 'In ([0-9]+) decks\n([0-9]+)% of ([0-9]+) decks'

        if response.get('redirect', None):
            response = requests.get(f'https://json.edhrec.com/pages{response["redirect"]}.json')
            response = response.json()

        match = re.match(edhrec_pattern, response['container']['json_dict']['card']['label'])

        if match:
            return {
                'name': original_card_name,
                'labels': response['container']['json_dict']['card']['label'].split('\n'),
                'numIncluded': int(match.groups()[0]),
                'numDecks': int(match.groups()[2]),
                'labelPercentage': int(match.groups()[1])
            }
        elif response['container']['json_dict']['card']['label'] == '0 decks':
            return {
                'name': original_card_name,
                'labels': ['0 decks'],
                'numIncluded': 0,
                # Todo: Retrieve number of decks
                'numDecks': float('nan'),
                'labelPercentage': 0
            }
        else:
            raise ValueError("unable to interpret label")

    except:
        raise Exception(f'error while trying to fetch {original_card_name if original_card_name else card_name}')


@app.route('/')
def main():  # put application's code here
    return render_template('index.html', tiers=tiers)


@app.route('/', methods=['POST'])
def get_score():
    try:
        decklist_text = request.form.get('decklist')
        skip_basics = 'skipBasics' in request.form.keys()
        skip_wastes = 'skipWastes' in request.form.keys()

        tier_breakpoints = {tier[1]: int(request.form.get(tier[1], tier[2])) for tier in tiers}
        decklist = decklist_text.splitlines()
        decklist = [entry.split("(")[0] for entry in decklist]
        number_pattern = "([0-9]+)?[x\*]? ?(.*)"
        decklist_groups = [re.match(number_pattern, entry).groups() for entry in decklist]
        decklist = [(parse_int(group[0], 1), group[1].strip()) for group in decklist_groups]
        if skip_basics:
            decklist = list(filter(lambda entry: entry[1].lower() not in basic_names, decklist))
        if skip_wastes:
            decklist = list(filter(lambda entry: entry[1].lower() != 'wastes', decklist))

        decklist_new = []
        errors = []

        for card in decklist:
            try:
                decklist_new.append((card[0], fetch_edhrec_data(card[1])))
            except Exception as e:
                errors.append(str(e))
        decklist = decklist_new
        sum_cards = sum(map(lambda card: card[0], decklist))
        output = {}

        for index, (_, tier, _) in enumerate(tiers):
            tier_cards = []

            for card in decklist:
                if index != 0:
                    prev_tier = tiers[index - 1][1]
                    if card[1]['labelPercentage'] >= tier_breakpoints[prev_tier]:
                        continue

                if card[1]['labelPercentage'] < tier_breakpoints[tier]:
                    continue

                tier_cards.append(card)

            n_cards = sum(map(lambda card: card[0], tier_cards))
            if sum_cards > 0:
                percentage = n_cards / sum_cards
            else:
                percentage = 0

            output[tier] = {
                'n_cards': n_cards,
                'percentage': percentage,
                'cards': list(map(lambda card: {
                    'name': card[1]['name'],
                    'n_cards': card[0],
                    'percentage': card[1]['labelPercentage']
                }, tier_cards)),
                'breakpoint': f'{tier_breakpoints[tier]}%'
            }

        return render_template(
            'tiers.html',
            tiers=[(tier[0], tier[1]) for tier in tiers],
            tier_mapping=output,
            decklist=list(decklist),
            errors=errors
        )
    except Exception as error:
        return render_template('error.html', error=str(error))


if __name__ == '__main__':
    app.run()
