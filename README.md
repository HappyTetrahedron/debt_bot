# debt_bot
Telegram bot to keep track of debts - remember who still owes you money easily

Check out the [official instance](https://t.me/dodecahedron_bot) if all you want is to use this bot

## Usage

The bot tries its best to understand english sentences. So if you borrowed money to telegram user `@bob14`, you can register this transaction by saying
```
I gave 15 to bob14 for pizza
```
or 
```
bob14 owes me 40 for groceries
```

When `@bob14` returns the money, simply register another transaction:
```
bob14 gave me 15 for the pizza
```
Or alternatively, if `@bob14` just gave you some cash to cancel all their debts, use:
```
bob14 gave me 55 in cash
```

To see an overview of all the debts between you and others, use the `\debts` command.
If you want to view the transaction history between you and another user, you can use the `\history` command, e.g., `\history bob14`

If you have friends with really long or hard-to-type telegram names, you can register an alias for them:
```
\alias luke = luke_at_my_really_long_username
```

### Registration
The debt bot doesn't know every person on telegram. If you want to enter a transaction with a friend who has never used the debt bot before, 
you will have to ask them to register first.

Registering is super easy: when you search for the bot on Telegram and click the "start" button, you're automatically registered. 
In case that doesn't work, you can also try the `\register` command. Once your friend is registered, you should be able to enter transactions with them.

### My friend doesn't have a telegram username, what do?
Use their full name (first and last name) as they have provided it to telegram. The debt bot will try its best to figure out who you're referring to, and give
you a list of users to choose from.

However, if someone shares the exact same name as your friend, you'll have no way of telling which one's the correct user. In that case, maybe just ask your friend 
to create a username? If they do, they'll have to `\register` again, otherwise the debt bot won't learn about their fancy new username.

### A note on currency
You may have noticed that the amounts you owe and lend do not have any currency information  - it's just a number. 
This was a deliberate choice to keep the system simple and flexible. I recommend you always enter all amounts in the currency 
you use every day - whether that's dollars, euros, pesos, or paper clips. If you at some point use a different currency, you can
convert it before entering it into the bot.

If you and your friends use different currencies, or you use different currencies very often, then this bot is not good enough for you. Sorry!


## Running it yourself

But you're here on my Github, so perhaps you wanted to run your own debt bot instance?
Feel free! Simply install the required python packages from `requirements.txt` and then create a config file for your bot.

The config file looks like this:
```
token: "123456789:ThisIsYourTelegramBotSecretToken1234"
db: "debts.db" 
```
The `db` entry is the path of the SQLite database in which debt information is stored. Provide a file name, and a sqlite file will automatically be created.
