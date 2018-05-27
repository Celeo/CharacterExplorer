import logging

from flask import Flask, render_template, request, flash, redirect, url_for
from esipy import App, EsiClient, EsiSecurity

from lib import CharacterExplorer, all_esi_read_scopes


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
    return render_template('index.html', sso_go=esi_security.get_auth_uri(scopes=all_esi_read_scopes))


@app.route('/view', methods=['POST'])
def view():
    token = request.form.get('refresh_token')
    if not token:
        flash('No token supplied in request', 'warning')
        return redirect(url_for('index'))
    try:
        explorer = CharacterExplorer(esi_app, esi_security, esi_client, token)
        return render_template('view.html', explorer=explorer)
    except Exception as e:
        logging.exception('Could not load token data: ' + str(e))
        flash('Could not load token data', 'warning')
        return redirect(url_for('index'))


@app.route('/eve/callback')
def eve_callback():
    code = request.args.get('code')
    if not code:
        flash('Login unsuccessful', 'warning')
        return redirect(url_for('index'))
    try:
        tokens = esi_security.auth(code)
    except:
        flash('Could not get refresh token', 'warning')
        return redirect(url_for('index'))
    return render_template('token_show.html', token=tokens['refresh_token'])


@app.template_filter('mail_recipients')
def filter_mail_recipients(data):
    return ', '.join([r['recipient_name'] for r in data])
