import re
import json
import logging
import datetime

HELP_FORMAT = """:cow2: usage:

{pattern.pattern}: ... - channel messages
... - direct messages

*everyone*
{help.pattern} - this message
{stats.pattern} - statistics
{patterns}

*master only*
{loglevel.pattern} - gets/sets the loglevel
{restart.pattern} - restarts moobot
"""
STATS_FORMAT = """:cow2: stats:

:speech_balloon: #messages: {messages}
:bust_in_silhouette: #known users: {users}
:slack: #known channels: {channels}

uptime: {uptime}
"""


outputs = []
config = {}
channels = {}
users = {}
logger = logging.getLogger(__name__)

class Generic(object):
    def __init__(self, d):
        for (k, v) in d.iteritems():
            if type(v) is dict:
                d[k] = Generic(v)
        self.__dict__.update(d)

    def __repr__(self):
        return repr(self.__dict__)

stats = Generic({
    'messages': 0,
    'started': None
})


def setup():
    config['pattern'] = re.compile('<@{id}>'.format(**config), re.IGNORECASE)
    config['restart'] = re.compile('{restart}'.format(**config), re.IGNORECASE)
    config['loglevel'] = re.compile('{loglevel}'.format(**config), re.IGNORECASE)
    config['help'] = re.compile('{help}'.format(**config), re.IGNORECASE)
    config['stats'] = re.compile('{stats}'.format(**config), re.IGNORECASE)
    trigger = config['trigger']
    for (k, v) in trigger.iteritems():
        v['pattern'] = re.compile(v['pattern'])

    logger.info('Started')
    stats.started = datetime.datetime.now()

    process_message(config['master'])


def get(method, key, **kwargs):
    res = json.loads(bot.slack_client.api_call(method, **kwargs))

    if key in res:
        return Generic(res[key])

    return None


def get_user(user_id):
    if user_id not in users:
        users[user_id] = get('users.info', 'user', user=user_id)
    return users[user_id]


def get_channel(channel_id):
    if channel_id not in channels:
        channels[channel_id] = get('channels.info', 'channel', channel=channel_id)
    return channels[channel_id]


def moo(channel, user, text, message):
    outputs.append([channel.id, message])
    stats.messages += 1
    logger.info('I mooed for {1} in channel #{0} ({2})'.format(channel.name, user.name, text))


def get_response(channel, user, text):
    for (k, v) in config['trigger'].iteritems():
        if v['pattern'].search(text):
            return v['response']
    return config['default']


def check_action(channel, user, text):
    if config['help'].search(text):
        s = []
        for (k, v) in config['trigger'].iteritems():
            s.append('{pattern.pattern} - {response}'.format(**v))

        moo(
            channel,
            user,
            text,
            HELP_FORMAT.format(patterns='\n'.join(s), **config)
        )

        return True

    if config['restart'].match(text):
        if user.id != config['master']['user']:
            moo(channel, user, text, config['master']['denied'])
            return

        logger.info('I\'m restarting for %s in channel #%s (%s)', user.name, channel.name, text)

        import sys
        sys.exit(0)

    m = config['loglevel'].match(text)
    if m:
        if user.id != config['master']['user']:
            moo(channel, user, text, config['master']['denied'])
            return

        value = m.group('loglevel')
        if value is not None:
            value = value.upper().strip()
        level = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARN': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }.get(value)

        if level is not None:
            logger.info('Set loglevel for %s in channel #%s (%s)', user.name, channel.name, text)
            logging.getLogger('__main__').setLevel(level)
            logger.setLevel(level)

            moo(
                channel,
                user,
                text,
                ':cow2: loglevel changed to {}'.format(
                    logging.getLevelName(level)
                )
            )
        else:
            logger.info('Showing loglevel for %s in channel #%s (%s)', user.name, channel.name, text)
            moo(
                channel,
                user,
                text,
                ':cow2: loglevel is {}'.format(
                    logging.getLevelName(logger.getEffectiveLevel())
                )
            )

        return True

    if config['stats'].search(text):
        moo(
            channel,
            user,
            text,
            STATS_FORMAT.format(
                users=len(users.keys()),
                channels=len(channels.keys()),
                uptime=str(datetime.datetime.now() - stats.started),
                **stats.__dict__)
        )

        return True

    return False


def process_message(message):
    logger.info(repr(message))
    if 'text' in message and 'channel' in message and 'user' in message:
        user = get_user(message['user'])
        channel = get_channel(message['channel'])
        if channel is None:
            channel = Generic({
                'id': message['channel'],
                'name': user.name,
                'is_channel': False
            })
        text = message['text']
        if (user.name != 'moobot'
                and (
                    not channel.is_channel
                    or config['pattern'].search(text)
                )):
            if not check_action(channel, user, text):
                moo(channel, user, text, get_response(channel, user, text))
