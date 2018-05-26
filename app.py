from flask import Flask, render_template, request
from esipy import App, EsiClient, EsiSecurity

from lib import CharacterExplorer


app = Flask(__name__)
app.config.from_json('config.json')

esi_headers = {'User-Agent': 'EVE Character Explorer | celeodor@gmail.com'}
esi_app = App.create('https://esi.tech.ccp.is/latest/swagger.json?datasource=tranquility')
esi_security = EsiSecurity(
    app=esi_app,
    client_id=app.config['CLIENT_ID'],
    secret_key=app.config['SECRET_KEY'],
    redirect_uri=app.config['REDIRECT_URI'],
    headers=esi_headers
)
esi_client = EsiClient(
    security=esi_security,
    headers=esi_headers
)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/view', methods=['POST'])
def view():
    print(request.form['refresh_token'])
    explorer = CharacterExplorer(esi_app, esi_security, esi_client, request.form['refresh_token'])
    return render_template('view.html', explorer=explorer)


@app.template_filter('mail_recipients')
def filter_mail_recipients(data):
    return ', '.join([r['recipient_name'] for r in data])
