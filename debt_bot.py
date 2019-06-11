#!/usr/bin/env python
# -*- coding: utf-8 -*-
import random
import re
import yaml
import logging
import dataset
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Match this first, because the X_TO_ME regex will capture stuff that should be parsed by this one.
I_TO_X_PATTERN = re.compile(
    '^i?\s*(g[ia]ve|g[eo]t|owe[sd]?)\s+(-?\d+\.?\d*)\s+(?:to|from)?\s*@?(.+?)(?:\s+((?:because(?:\s+of)?|for|in)\s+.*))?$',
    flags=re.I
)
I_GIVE_X_PATTERN = re.compile(
    '^i?\s*(g[ia]ve|owe[sd]?)\s+@?(.+?)\s+(-?\d+\.?\d*)\s*((?:because(?:\s+of)?|for|in)\s*.*)?$',
    flags=re.I
)
# This will falsely match the "I gave X to Y" pattern as well, so match the other one before this
X_TO_ME_PATTERN = re.compile(
    '^\s*@?(.+?)\s+(g[ia]ve|g[eo]t|owe[sd]?)\s+(?:me)?\s*(-?\d+\.?\d*)(?:\s+(?:to|from)?\s*me\s*)?\s*((?:because(?:\s+of)?|for)?\s*.*)$',
    flags=re.I
)

# Match this one last
SHORTHAND_PATTERN = re.compile(
    '^@?(.+?)\s*(-?\d+\.?\d*)\s*(.+)?$',
    flags=re.I
)

ALIAS_PATTERN = re.compile(
    '^\/alias\s+(.+?)\s*=\s*@?(.+?)\s*$',
    flags=re.I
)

RECEIVE_PATTERN = re.compile('g[eo]t|owe[sd]?', re.I)

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

HISTORY_CMD = "h"
DEBT_CMD = "d"
TRANSACTION_CMD = "g"
ALIAS_CMD = "a"


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

    @staticmethod
    def get_affirmation():
        return random.choice(AFFIRMATIONS)

    @staticmethod
    def parse_message(message):
        match = I_TO_X_PATTERN.match(message)
        if match:
            groups = match.groups()
            direction = groups[0]
            amount_str = groups[1]
            recipient = groups[2]
            reason = groups[3]
            amount = float(amount_str)
        else:
            match = X_TO_ME_PATTERN.match(message)
            if match:
                groups = match.groups()
                direction = groups[1]
                amount_str = groups[2]
                recipient = groups[0]
                reason = groups[3]
                amount = float(amount_str) * -1  # direction in the regex is reversed, so unreverse here for uniformity
            else:
                match = I_GIVE_X_PATTERN.match(message)
                if match:
                    groups = match.groups()
                    direction = groups[0]
                    amount_str = groups[2]
                    recipient = groups[1]
                    reason = groups[3]
                    amount = float(amount_str)
                else:
                    match = SHORTHAND_PATTERN.match(message)
                    if not match:
                        return None, None, None
                    groups = match.groups()
                    direction = 'give'
                    amount_str = groups[1]
                    recipient = groups[0]
                    reason = 'for ' + groups[2] if groups[2] else None
                    amount = float(amount_str)

        if RECEIVE_PATTERN.match(direction):
            amount *= -1

        return str(amount), recipient, reason or ""

    def send_message(self, bot, message, recipient=None):
        if not recipient:
            if (not isinstance(message, dict)) or 'chat_id' not in message:
                raise ValueError("Unknown recipient")

        if isinstance(message, dict):
            bot.send_message(
                chat_id=recipient or message['chat_id'],
                text=message.get('message'),
                reply_markup=message.get('markup'),
            )
            if 'other_message' in message:
                self.send_message(bot, message['other_message'])
        else:
            bot.send_message(
                chat_id=recipient,
                text=message,
            )

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
        if abs(debt) <= 0.001:
            return "You and {} are {}even.".format(name, word)
        return self.bidir_format("{} " + word + "owes you {:.2f}.",
                                 "You " + word + "owe {} {:.2f}.",
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
            string += self.bidir_format(":  You gave {} {:.2f}",
                                        ":  {} gave you {:.2f}",
                                        name,
                                        item['amount'] if item['creditor'] == uid1 else -item['amount'])
            if 'reason' in item and item['reason']:
                string += " {}".format(item['reason'])
            string += ".\n"

        if not string:
            return "You and {} don't have any transactions so far.".format(name)
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
        if not summary:
            return "Congratulations! You currently don't have any debts."
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

    def get_user(self, user_id):
        users = self.db['users']
        recipient = users.find_one(user_id=user_id)
        return recipient

    def get_alias(self, owner_id, alias):
        aliases = self.db['aliases']
        return aliases.find_one(owner_id=owner_id, alias=alias)

    def delete_alias(self, owner_id, alias):
        aliases = self.db['aliases']
        aliases.delete(owner_id=owner_id, alias=alias)

    def get_all_aliases(self, owner_id):
        aliases = self.db['aliases']
        users = self.db['users']
        all_aliases = aliases.find(owner_id=owner_id)

        str_aliases = []
        for alias in all_aliases:
            target_user = users.find_one(user_id=alias['target_id'])
            str_aliases.append("{} points to {} {}".format(
                alias['alias'],
                target_user['first_name'] or "",
                target_user['last_name'] or "",
            ))

        return str_aliases

    # Commands
    def dispatch_command_for_user(self, command, initiator_id, username_str, other_args=None, use_alias=True):
        if not other_args:
            other_args = []
        username_str = username_str.strip().lower()
        alias = None

        if use_alias:
            alias = self.get_alias(initiator_id, username_str)

        users = self.db['users']
        if alias:
            target_user = users.find_one(user_id=alias['target_id'])
        else:
            target_user = users.find_one(username_lower=username_str)

        if target_user:
            return self.dispatch_command(command, initiator_id, target_user, other_args)

        else:
            callback_data = command + ":{}:" + ':'.join(other_args)

            recipient_parts = username_str.split()
            recipient_str = " ".join(recipient_parts)

            potential_recipients = None
            if len(recipient_parts) >= 2:
                first = recipient_parts[0]
                last = recipient_parts[-1]
                potential_recipients = self.db.query(
                    "SELECT * FROM users "
                    "WHERE (first_name LIKE '{}%' "
                    "AND last_name LIKE '%{}%') "
                    "OR first_name + ' ' + last_name LIKE '{}%'".format(
                        first, last, recipient_str
                    )
                )
                potential_recipients = list(potential_recipients)  # fuck this stupid BS

            if not potential_recipients:
                potential_recipients = self.db.query(
                    "SELECT * FROM users "
                    "WHERE first_name LIKE '{}%' "
                    "OR last_name LIKE '{}%' "
                    "OR first_name + ' ' + last_name LIKE '{}%'".format(
                        recipient_str, recipient_str, recipient_str
                    )
                )

            buttons = []
            for row in potential_recipients:
                buttons.append([
                    InlineKeyboardButton("{} {}".format(row['first_name'] if row['first_name'] else "",
                                                        row['last_name'] if row['last_name'] else ""),
                                         callback_data=callback_data.format(
                                             row['user_id']
                                         ))
                ])
            if len(buttons) == 0:
                return "I'm sorry, I couldn't find anyone named {}. Perhaps you need to ask them to register?".format(
                    recipient_str
                )
            buttons.append([InlineKeyboardButton("None of these people", callback_data=callback_data.format('0'))])
            markup = InlineKeyboardMarkup(buttons)
            return {
                "message": "{} doesn't appear to be a valid username, but I found some people that could be them. \n" \
                           "Please select them from below:".format(recipient_str),
                "markup": markup,
            }

    def dispatch_command(self, command, initiator_id, target_user, args):
        if command == TRANSACTION_CMD:
            if len(args) < 2:
                return "Aw no, something went wrong. Please try again."

            amount = float(args[0])
            reason = args[1] or None

            return self.transaction_command(initiator_id, target_user, amount, reason)

        if command == HISTORY_CMD:
            return self.history_command(initiator_id, target_user)

        if command == DEBT_CMD:
            return self.debt_command(initiator_id, target_user)

        if command == ALIAS_CMD:
            if len(args) < 1:
                return "Something is broken, sorry. Please try again."
            alias = args[0]
            return self.alias_command(initiator_id, target_user, alias)

    def transaction_command(self, sender_id, recipient, amount, reason):
        transaction = {
            'creditor': sender_id if amount > 0 else recipient['user_id'],
            'debitor': recipient['user_id'] if amount > 0 else sender_id,
            'amount': abs(amount),
            'reason': reason,
            'timestamp': datetime.datetime.now(),
        }

        transactions = self.db['transactions']
        transactions.insert(transaction)

        msg = self.bidir_format("You gave {} {:.2f}",
                                "{} gave you {:.2f}",
                                recipient['first_name'],
                                amount)
        if reason:
            msg += " {}".format(reason)
        msg += ".\n\n"

        msg += self.get_debt_string(sender_id, recipient['user_id'], recipient['first_name'], 'now')
        sender = self.get_user(sender_id)

        other = self.bidir_format("{} got {:.2f} from you",
                                  "{} gave you {:.2f}",
                                  sender['first_name'],
                                  -amount)
        if reason:
            other += " {}".format(reason)
        other += ".\n\n"

        other += self.get_debt_string(recipient['user_id'], sender_id, sender['first_name'], 'now')

        if recipient['user_id'] is None:
            return "Oh no, something went wrong"

        return {
            'answer': self.get_affirmation(),
            'message': msg,
            'other_message': {
                'chat_id': recipient['user_id'],
                'message': other
            }
        }

    def history_command(self, sender_id, recipient):
        msg = self.get_debt_history_string(sender_id,
                                           recipient['user_id'],
                                           recipient['first_name'])
        msg += '\n'
        msg += self.get_debt_string(sender_id, recipient['user_id'], recipient['first_name'])
        return {
            'message': msg,
            'answer': self.get_affirmation()
        }

    def debt_command(self, sender_id, recipient):
        msg = self.get_debt_string(sender_id,
                                   recipient['user_id'],
                                   recipient['first_name'],
                                   'currently')
        return {
            'message': msg,
            'answer': self.get_affirmation(),
        }

    def alias_command(self, owner_id, target_user, alias):
        aliases = self.db['aliases']
        old_alias = self.get_alias(owner_id, alias)
        new_alias = {
            'owner_id': owner_id,
            'target_id': target_user['user_id'],
            'alias': alias.strip(),
        }

        aliases.upsert(new_alias, ['owner_id', 'alias'])

        msg = "Your alias '{}' has been {} to point to {} {}.".format(
            alias,
            "updated" if old_alias else "created",
            target_user['first_name'] or "",
            target_user['last_name'] or "",
            )

        return {
            'message': msg,
            'answer': 'Alias created.'
        }

    # Conversation handlers:
    def handle_register(self, bot, update):
        if self.register_user(update.message.from_user, force=True):
            update.message.reply_text('Hi! Thanks for registering with Debt Bot. '
                                      'People can now register their debts with you.')
        else:
            update.message.reply_text("Looks like you're already registered. You're good to go!")

    def handle_history(self, bot, update):
        arguments = update.message.text.split(maxsplit=1)

        if len(arguments) < 2:
            update.message.reply_text("Please give me the name of the person for which you want to know "
                                      "the transaction history.")
            return
        username = arguments[1]
        if username.startswith('@'):
            username = username[1:]

        self.send_message(
            bot,
            self.dispatch_command_for_user(HISTORY_CMD, update.message.from_user.id, username),
            update.message.from_user.id,
        )

    def handle_debts(self, bot, update):
        arguments = update.message.text.split(maxsplit=1)

        if len(arguments) > 1:
            username = arguments[1]
            if username.startswith('@'):
                username = username[1:]

            self.send_message(
                bot,
                self.dispatch_command_for_user(DEBT_CMD, update.message.from_user.id, username),
                update.message.from_user.id,
            )

        else:
            update.message.reply_text(self.get_all_debts(update.message.from_user.id))

    def handle_inline_button(self, bot, update):
        query = update.callback_query
        data = update.callback_query.data
        data = data.split(':', 3)

        cmd = data[0]
        userid = data[1]
        args = data[2:]

        message_id = query.message.message_id
        chat_id = query.message.chat.id

        if userid == '0':
            query.answer("Action cancelled")
            bot.edit_message_text(text="Looks like the person you wanted to find isn't registered :(",
                                  message_id=message_id,
                                  chat_id=chat_id)
            return

        users = self.db['users']
        recipient = users.find_one(user_id=userid)
        if not recipient:
            query.answer("Uh oh, something went pretty wrong here")
            return

        reply = self.dispatch_command(cmd, query.from_user.id, recipient, args)

        if isinstance(reply, dict):
            if 'message' in reply:
                bot.edit_message_text(text=reply['message'], message_id=message_id, chat_id=chat_id,
                                      reply_markup=reply.get('markup'))
            if 'answer' in reply:
                query.answer(reply['answer'])
            if 'other_message' in reply:
                self.send_message(bot, reply['other_message'])

    def handle_message(self, bot, update):
        if update.message.text is None:
            update.message.reply_text(self.get_affirmation())
            return
        self.register_user(update.message.from_user)

        amount, recipient_str, reason = self.parse_message(update.message.text)
        if not recipient_str:
            update.message.reply_text("Sorry, I could not understand your message at all :(")

        self.send_message(
            bot,
            self.dispatch_command_for_user(TRANSACTION_CMD,
                                           update.message.from_user.id,
                                           recipient_str,
                                           [amount, reason]),
            update.message.from_user.id,
        )

    def handle_alias(self, bot, update):
        message = update.message.text.strip().lower()
        if message == "/alias":
            all_aliases = self.get_all_aliases(update.message.from_user.id)
            if not all_aliases:
                update.message.reply_text("You don't seem to have any aliases. "
                                          "You can create them by typing\n"
                                          "/alias nickname = @username")
                return
            update.message.reply_text("Your aliases:\n\n{}".format('\n'.join(all_aliases)))
            return
        match = ALIAS_PATTERN.match(message)
        if not match:
            update.message.reply_text("I'm sorry, I couldn't understand that. Try the following:\n"
                                      "/alias nickname = @username")
            return
        groups = match.groups()
        alias = groups[0]
        username = groups[1]

        response = self.dispatch_command_for_user(
            ALIAS_CMD,
            update.message.from_user.id,
            username, [alias],
            use_alias=False
        )

        self.send_message(bot, response, update.message.from_user.id)

    def handle_unalias(self, bot, update):
        message = update.message.text.strip().lower()
        message_parts = message.split(maxsplit=1)

        if len(message_parts) < 2:
            update.message.reply_text("Sorry, I don't understand which alias you want to delete.\n"
                                      "Try: /unalias nickname")
            return
        alias = message_parts[1]
        old_alias = self.get_alias(update.message.from_user.id, alias)

        if not old_alias:
            update.message.reply_text("You don't seem to have an alias named {}.".format(alias))
            return

        self.delete_alias(update.message.from_user.id, alias)
        target_user = self.get_user(old_alias['target_id'])
        update.message.reply_text("Your alias '{}' for {} {} has been deleted.".format(
            alias,
            target_user['first_name'] or "",
            target_user['last_name'] or "",
        ))

    # Help command handler
    def handle_help(self, bot, update):
        """Send a message when the command /help is issued."""
        helptext = "I'm a debt bot! I can keep track of your debts!\n\n" \
                   "In order to use me, you first have to /register. " \
                   "After that, you can send me transactions with other people " \
                   "(given they are also registered), and I will keep track of who owes money to whom. \n\n" \
                   "Example: \n" \
                   "I gave 15 to bob14 for pizza \n" \
                   "bob14 owes me 40 for groceries \n" \
                   "bob14 gave me 12.30 for the cinema ticket\n\n" \
                   "To see all your debts, use: /debts\n" \
                   "To see debts with a specific person, use: /debts _username_\n" \
                   "To see a transaction history, use: /history _username_\n" \
                   "To create an alias, use: /alias _nickname_ = _username_\n" \
                   "To delete an alias, use: /unalias _nickname_\n" \
                   "You can use the nickname in place of the username for any other command after creating" \
                   "an alias."

        update.message.reply_text(helptext, parse_mode="Markdown")

    # Error handler
    def handle_error(self, bot, update, error):
        """Log Errors caused by Updates."""
        logger.warning('Update "%s" caused error "%s"', update, error)

    def run(self, opts):
        with open(opts.config, 'r') as configfile:
            config = yaml.load(configfile, Loader=yaml.FullLoader)

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

        dp.add_handler(CommandHandler("alias", self.handle_alias))
        dp.add_handler(CommandHandler("unalias", self.handle_unalias))

        dp.add_handler(CommandHandler("help", self.handle_help))

        dp.add_handler(CallbackQueryHandler(self.handle_inline_button))

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
