# Import libraries

from datetime import date
from email.mime import text
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders, message
from flask import Flask, app, flash, request, redirect, url_for, session, jsonify, render_template
from flask.wrappers import Response
from flask_cors import CORS, cross_origin
import pandas as pd
import random
import os
import json
import nltk
import sqlite3
import email
import smtplib
import ssl
from nltk import tokenize
from nltk.sentiment.vader import SentimentIntensityAnalyzer
nltk.download('vader_lexicon')

# Create application object as an instance of class Flask

app = Flask(__name__)

# Configuration

app.config['CORS_HEADERS'] = 'Content-Type'

# Allow CORS for all domains on all routes

cors = CORS(app)

# Decorators


@app.route('/moodUp', methods=['POST'])
@cross_origin()
# Functions
def moodUp():
    moods = request.form
    bmis_df = up_bmis(moods, init_bmis())
    ques = random.sample(init_ques_dict()[get_mood(bmis_df)], 1)[0]
    return jsonify(
        value=ques,
        moods=moods
    )


def build_res(response):
    return jsonify(
        value=response,
        finished="false"
    )

# Decorators


@app.route('/sendMsg', methods=['POST'])
@cross_origin()
# Functions
def sendMessage():
    is_final = request.form.get('isFinal') == 'true'
    message = request.form.get('message')
    moods = json.loads(request.form.get('moods'))
    mood_tuple = get_mood(up_bmis(moods, init_bmis()))
    followup, rant = issue_followup(mood_tuple, message)
    if is_final:
        if rant:
            followup = 'Thanks for opening up to me! I will keep this for you to look back on. I hope you have a better day tomorrow :) Goodnight!'
        else:
            followup = 'Those are great goals! I will be sure to email those to you as a reminder, so you know what you need to accomplish to have a great day tomorrow. Goodnight!'
            send_mail(message, request.form.get('email'))
        return jsonify(
            value=followup,
            finished="true"
        )
    return build_res(followup)

# Decorators


@app.route('/sendRecap', methods=['POST'])
@cross_origin()
# Functions
def sendRecap():
    message = json.loads(request.form.get("messages"))
    message_string = '~'.join(message)
    moods = json.loads(request.form.get('moods'))
    mood_tuple = get_mood(up_bmis(moods, init_bmis()))
    mood_str = mood_tuple[0]+'&'+mood_tuple[1]
    email = request.form.get("email")
    date = json.loads(request.form.get("date"))
    connection = sqlite3.connect("user_hist.db")
    create_cmd = """
        CREATE TABLE IF NOT EXISTS interaction_with_users(
        user_email VARCHAR(100),
        user_mood VARCHAR(30),
        date VARCHAR(60),
        interaction VARCHAR(1000))
        ;
        """
    cursor = connection.cursor()
    cursor.execute(create_cmd)
    insert_cmd = """
        INSERT INTO interaction_with_users(user_email, user_mood, date, interaction)
        VALUES("[{email}]", "{mood_str}", "{date}", "{messages}")
        ;
        """
    insert_cmd_formatted = insert_cmd.format(
        email=email, mood_str=mood_str, date=date, messages=message_string)
    cursor.execute(insert_cmd_formatted)
    connection.commit()
    connection.close()
    return app.response_class(
        response="Received Recap.",
        status=200,
        mimetype='application/json',
    )

# Decorators


@app.route('/getHistory', methods=['POST'])
@cross_origin()
# Functions
def getHistory():
    final_result_list = []
    email = request.form.get("email")
    print(email)

    connection = sqlite3.connect("user_hist.db")
    cursor = connection.cursor()
    format_str = """
                SELECT user_mood, date, interaction FROM interaction_with_users
                WHERE interaction_with_users.user_email = "[{email}]"
                ;
                """
    get_cmd = format_str.format(email=email)
    cursor.execute(get_cmd)
    results = cursor.fetchall()
    for result in results:
        messages_array = result[2].split('~')
        final_result_list.append((result[0], result[1], messages_array))
    print(final_result_list)
    return jsonify(
        content=final_result_list
    )

# BMIS


def init_bmis():
    moods = ['Lively', 'Happy', 'Sad', 'Tired', 'Caring', 'Contect', 'Gloomy', 'Jittery',
             'Drowsy', 'Grouchy', 'Peppy', 'Nervous', 'Calm', 'Loving', 'Fed Up', 'Active']
    un_pleasant = [1, 1, -1, -1, 1, 1, -1, -1, -1, -1, 1, -1, 1, 1, -1, 1]
    arousal_calm = [1, 0, 1, -1, 1, 0, 1, 1, 0, 0, 1, 1, -1, 1, 1, 1]
    bmis_df = pd.DataFrame(
        data={'mood': moods, 'pleasant_unpleasant': un_pleasant, 'arousal_calm': arousal_calm})
    return bmis_df


def up_bmis(moods, dataframe):
    dataframe['answer'] = [0]*len(dataframe)
    for mood in moods:
        if mood != 'email':
            dataframe.loc[dataframe['mood'] ==
                          mood, 'answer'] = int(moods[mood])
    return dataframe


def get_mood(dataframe):
    score = {'pleasant_unpleasant': (dataframe['pleasant_unpleasant']*dataframe['answer']).sum(
    ), 'arousal_calm': (dataframe['arousal_calm']*dataframe['answer']).sum()}
    ms_tuple = (None, None)

    # arousal_calm => -16 down, 16 up
    # pleasant_unpleasant => -10 down, 10 up
    if score['pleasant_unpleasant'] > 10 and score['arousal_calm'] > 16:
        ms_tuple = ('positive', 'aroused')
    elif score['pleasant_unpleasant'] > 10 and score['arousal_calm'] <= 16:
        ms_tuple = ('positive', 'calm')
    elif score['pleasant_unpleasant'] >= -10 and score['arousal_calm'] > 16:
        ms_tuple = ('neutral', 'aroused')
    elif score['pleasant_unpleasant'] >= -10 and score['arousal_calm'] <= 16:
        ms_tuple = ('neutral', 'calm')
    elif score['arousal_calm'] > 16:
        ms_tuple = ('negative', 'aroused')
    else:
        ms_tuple = ('negative', 'calm')

    return ms_tuple


def init_ques_dict():
    types = [('positive', 'aroused'),
             ('positive', 'calm'),
             ('neutral', 'aroused'),
             ('neutral', 'calm'),
             ('negative', 'aroused'),
             ('negative', 'calm')]
    positive_addon = "I am so happy to hear that your day went well!!"
    neutral_addon = "Hmm..Seems like it was a normal day for you. Your mood is pretty neutral."
    negative_addon = "I am so sorry to hear that your day didn't go as planned. But don't worry, I'm here for you. Let's try to be positive."
    ques = [{positive_addon+'What made you smile today?', positive_addon+'What made your day bright?', positive_addon+'Did something happen today that you would like to share?'},
            {positive_addon+'What kept you peaceful today?', positive_addon +
                'What did you do today that you found relaxing?', 'What was the most enjoyable part of your day?'},
            {neutral_addon+'When did you feel appreciated today?', neutral_addon +
                'What was the hardest part of your day?', neutral_addon+'What do you wish went differently today?'},
            {neutral_addon+"What did you want to accomplish today that you didn't get to?", neutral_addon +
                'What helped you feel relaxed today?', neutral_addon+'Who are you grateful for today?'},
            {negative_addon+'What did you do to take care of yourself today?', negative_addon +
                'How were you kind to yourself or to others today?', negative_addon+'How did you feel loved today?'},
            {negative_addon+'What made you want to get out of bed today?', negative_addon+'What is your plan for tomorrow?', negative_addon+'Do you want share something? Sometimes sharing things makes everything a lot easier.'}]

    ques_dict = dict()
    for i in range(len(types)):
        ques_dict[types[i]] = ques[i]
    return ques_dict


def issue_followup(mood, text):
    scores = SentimentIntensityAnalyzer().polarity_scores(text)
    followup = ''
    rant = False
    print(scores)
    if scores['neg'] > .3:
        if mood[0] == 'positive':
            followup = "I sense some negativity. Let me try to divert your mind. Tell me something about your favourite books or movies."
        elif mood[0] == 'neutral' or mood[0] == 'negative':
            followup = "I'm so sorry to hear that. I can understand your situation. Feel free to rant to me. I'm always here to listen."
            rant = True
    elif scores['pos'] > .3:
        followup = "I love this positivity!! Let's keep this up for tomorrow by making some plans or goals you wish to accomplish."
    elif scores['neu'] > .3:
        if mood[0] == 'positive' or mood[0] == 'neutral':
            followup = "Hmm... I see. Thank you for sharing that with me. Yeah, I'm sensing very neutral vibes. But let's use this as inspiration to have a better day tomorrow by coming up with some goals!"
        elif mood[0] == 'negative':
            followup = "I'm sorry that today was pretty meh. I'm always here for you. If you need to get something off your chest, then, please, go ahead."
            rant = True

    return followup, rant


def send_mail(plan, EMAIL):
    message = MIMEMultipart()
    message["From"] = EMAIL
    message["To"] = EMAIL
    message["Subject"] = "AI_BOT"
    message.attach(MIMEText(plan, "plain"))
    text = message.as_string()
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login("xyz@gmail.com", os.environ['EMAIL_PASSWORD'])
        server.sendmail("xyz@gmail.com", EMAIL, text)


app.run(port=5000, debug=True)
