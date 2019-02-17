#!/usr/bin/env python
# -*- coding: utf-8 -*-
import random
import re
import yaml
import logging
import dataset
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

PATTERN = re.compile(
    'i?\s*(g[ia]ve|g[eo]t)\s+(-?\d+\.?\d*)\s+(?:to|from)?\s*@?(\S+)\s*(?:because(?:\s+of)?|for)?\s*(.*)',
    flags=re.I
)

RECEIVE_PATTERN = re.compile('g[eo]t', re.I)

AFFIRMATIONS = [
    "Cool",
    "Nice",
    "Doing great",
    "Awesome",
    "Okey dokey",
    "Neat",
    "Whoo",
    "Wonderful",
    "Splendid",
]


class PollBot:
    def __init__(self):
        self.db = None

    def register_user(self, user, force=False):
        users = self.db['users']
        id = user.id
        stored = users.find_one(user_id=id)
        if not stored or force:
            new_user = {
                'user_id': id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'username_lower': user.username.lower() if user.username else None
            }
            print(new_user)
            users.upsert(new_user, ['user_id'])
        if not stored:
            return True
        return False

    def get_affirmation(self):
        return random.choice(AFFIRMATIONS)

    def parse_message(self, message):
        match = PATTERN.match(message)
        if not match:
            return False, False, False

        groups = match.groups()
        direction = groups[0]
        amount_str = groups[1]
        recipient = groups[2]
        reason = groups[3]

        amount = float(amount_str)

        if RECEIVE_PATTERN.match(direction):
            amount *= -1

        return amount, recipient, reason

    def analyze_message(self, message, sender):
        amount, recipient_str, reason = self.parse_message(message)
        if not recipient_str:
            return "Sorry, I could not understand your message at all :("
        users = self.db['users']
        recipient = users.find_one(username_lower=recipient_str.lower())

        if not recipient:
            return "Sorry, I don't know who {} is. Maybe you have to ask them to register?".format(recipient_str)

        transaction = {
            'creditor': sender.id if amount > 0 else recipient['user_id'],
            'debitor': recipient['user_id'] if amount > 0 else sender.id,
            'amount': abs(amount),
            'reason': reason,
            'timestamp': datetime.datetime.now()
        }

        transactions = self.db['transactions']
        transactions.insert(transaction)

        msg = self.bidir_format("You gave {} {}.",
                                "{} gave you {}.",
                                recipient['first_name'],
                                amount)
        msg += "\n\n"

        msg += self.get_debt_string(sender.id, recipient['user_id'], recipient['first_name'], 'now')
        return msg

    def get_debt(self, uid1, uid2):
        transactions = self.db['transactions']
        debt = 0.0

        given = transactions.find(creditor=uid1, debitor=uid2)
        for t in given:
            debt += t['amount']

        gotten = transactions.find(creditor=uid2, debitor=uid1)
        for t in gotten:
            debt -= t['amount']

        return debt

    def get_debt_string(self, uid1, uid2, name, word=""):
        if word:
            word += " "
        debt = self.get_debt(uid1, uid2)
        if debt == 0:
            return "You and {} are {}even.".format(name, word)
        return self.bidir_format("{} " + word + "owes you {}.",
                                 "You " + word + "owe {} {}.",
                                 name,
                                 debt)

    def get_debt_history(self, uid1, uid2):
        results = self.db.query('SELECT * FROM transactions '
                                'WHERE (creditor = :uid1 AND debitor = :uid2) '
                                'OR (creditor = :uid2 AND debitor = :uid1) '
                                'ORDER BY timestamp ASC',
                                uid1=uid1,
                                uid2=uid2)

        return list(results)

    def get_debt_history_string(self, uid1, uid2, name):
        history = self.get_debt_history(uid1, uid2)

        string = ""

        for item in history:
            if 'timestamp' in item and item['timestamp']:
                string += item['timestamp'].split()[0]
            string += self.bidir_format(":  You gave {} {}",
                                        ":  {} gave you {}",
                                        name,
                                        item['amount'] if item['creditor'] == uid1 else -item['amount'])
            if 'reason' in item and item['reason']:
                string += " for {}".format(item['reason'])
            string += ".\n"
        return string

    def get_all_debts(self, uid):
        all_others = []

        results = self.db.query('SELECT DISTINCT debitor FROM transactions WHERE creditor = :creditor', creditor=uid)
        for r in results:
            all_others.append(r['debitor'])

        results = self.db.query('SELECT DISTINCT creditor FROM transactions WHERE debitor = :debitor', debitor=uid)
        for r in results:
            if r['creditor'] not in all_others:
                all_others.append(r['creditor'])

        users = self.db['users']
        summary = ""
        for other in all_others:
            user = users.find_one(user_id=other)
            str = self.get_debt_string(uid, other, user['first_name'])
            if 'even' not in str:
                summary += str
                summary += "\n"

        return summary

    def bidir_format(self, str1, str2, name, amount):
        if amount > 0:
            return str1.format(name, abs(amount))
        else:
            return str2.format(name, abs(amount))

    def get_user_by_name(self, username):
        users = self.db['users']
        recipient = users.find_one(username_lower=username.lower())
        return recipient

    # Conversation handlers:
    def handle_register(self, bot, update):
        if self.register_user(update.message.from_user, force=True):
            update.message.reply_text('Hi! Thanks for registering with Debt Bot. '
                                      'People can now register their debts with you.')
        else:
            update.message.reply_text("Looks like you're already registered. You're good to go!")

    def handle_history(self, bot, update):
        arguments = update.message.text.split()

        if len(arguments) < 2:
            update.message.reply_text("Please give me the name of the person for which you want to know "
                                      "the transaction history.")
            return
        username = arguments[1]
        recipient = self.get_user_by_name(username)
        if not recipient:
            update.message.reply_text("Sorry, I don't know who {} is.".format(username))
            return
        msg = self.get_debt_history_string(update.message.from_user.id,
                                           recipient['user_id'],
                                           recipient['first_name'])
        msg += '\n'
        msg += self.get_debt_string(update.message.from_user.id, recipient['user_id'], recipient['first_name'])
        update.message.reply_text(msg)

    def handle_debts(self, bot, update):
        arguments = update.message.text.split()

        if len(arguments) > 1:
            username = arguments[1]
            recipient = self.get_user_by_name(username)
            if not recipient:
                update.message.reply_text("Sorry, I don't know who {} is.".format(username))
                return
            msg = self.get_debt_string(update.message.from_user.id,
                                       recipient['user_id'],
                                       recipient['first_name'],
                                       'currently')
            update.message.reply_text(msg)
            return

        update.message.reply_text(self.get_all_debts(update.message.from_user.id))

    def handle_message(self, bot, update):
        self.register_user(update.message.from_user)
        reply = self.analyze_message(update.message.text, update.message.from_user)
        update.message.reply_text(reply)

    # Help command handler
    def handle_help(self, bot, update):
        """Send a message when the command /help is issued."""
        helptext = "I'm a debt bot! I can keep track of your debts!\n\n" \
                   "In order to use me, you first have to /register. " \
                   "After that, you can send me transactions with other people " \
                   "(given they are also registered), and I will keep track of who owes money to whom. \n\n" \
                   "Example: \n" \
                   "I gave 15 to bob14 for pizza \n" \
                   "I got 12.30 from bob14 for the cinema ticket\n\n" \
                   "Please use the other person's username, or @mention them. People who don't have an " \
                   "username are currently not supported, unfortunately.\n\n" \
                   "To see all your debts, use: /debts\n" \
                   "To see debts with a specific person, use: /debts _username_\n" \
                   "To see a transaction history, use: /history _username_"

        update.message.reply_text(helptext, parse_mode="Markdown")

    # Error handler
    def handle_error(self, bot, update, error):
        """Log Errors caused by Updates."""
        logger.warning('Update "%s" caused error "%s"', update, error)

    def run(self, opts):
        with open(opts.config, 'r') as configfile:
            config = yaml.load(configfile)

        self.db = dataset.connect('sqlite:///{}'.format(config['db']))

        """Start the bot."""
        # Create the EventHandler and pass it your bot's token.
        updater = Updater(config['token'])

        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        dp.add_handler(CommandHandler("register", self.handle_register))
        dp.add_handler(CommandHandler("start", self.handle_register))

        dp.add_handler(CommandHandler("debts", self.handle_debts))

        dp.add_handler(CommandHandler("history", self.handle_history))

        dp.add_handler(CommandHandler("help", self.handle_help))

        dp.add_error_handler(self.handle_error)

        dp.add_handler(MessageHandler(None, self.handle_message))

        # Start the Bot
        updater.start_polling()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()


def main(opts):
    PollBot().run(opts)


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-c', '--config', dest='config', default='config.yml', type='string',
                      help="Path of configuration file")
    (opts, args) = parser.parse_args()
    main(opts)
