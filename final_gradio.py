# -*- coding: utf-8 -*-
"""gradio

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1mAe2iUCzoLwiCu7LK160MPA6Y2uxkRxD

## 前處理
"""

!pip install sentence-transformers
!pip install transformers torch

!pip install gradio

import pandas as pd
import numpy as np
import re
from matplotlib import pyplot as plt
from nltk.corpus import words
import nltk
from wordcloud import WordCloud
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from sklearn.feature_extraction.text import TfidfVectorizer
import xgboost as xgb
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler
from google.colab import files
import gradio as gr
from tabulate import tabulate
from transformers import pipeline

df = pd.read_csv('coursera_reviews.csv', encoding='ISO-8859-1')

# Retain only the relevant columns
df = df[['CourseId', 'Review', 'Label']]

# Drop rows with missing values in any of the relevant columns
df = df.dropna(subset=['CourseId', 'Review', 'Label'])

# Convert 'Label' to numeric (since it represents ratings) and check its datatype
df['Label'] = pd.to_numeric(df['Label'], errors='coerce')
df = df.dropna(subset=['Label'])  # Drop any rows where conversion failed
df = df[df['Review'].apply(lambda x: bool(re.match(r'^[\x00-\x7F]+$', str(x))))]

# Confirm the dataset structure after cleaning
df.info(), df.head()
num_courses = df['CourseId'].nunique()
num_courses

# 下載 NLTK 的英文單詞庫
nltk.download('words')
english_words = set(words.words())

# 定義改進的檢測函數
def is_fully_english_with_dict(text):
    words_in_text = re.findall(r'\b\w+\b', str(text))  # 提取單詞
    if not words_in_text:
        return False  # 空文本視為非英文
    english_word_count = sum(1 for word in words_in_text if word.lower() in english_words)
    return english_word_count / len(words_in_text) > 0.8  # 英文單詞比例超過 80%

# 篩選出完全英文的行
df['IsFullyEnglish'] = df['Review'].apply(is_fully_english_with_dict)
english_only_df = df[df['IsFullyEnglish']]

# 計算剩餘行數及所佔百分比
remaining_rows = len(english_only_df)
original_rows = len(df)
percentage_remaining = (remaining_rows / original_rows) * 100

print("剩下",remaining_rows, "筆資料")
print("佔原本資料",percentage_remaining,"%")

df = english_only_df.drop('IsFullyEnglish', axis=1)

from textblob import TextBlob

#df['SentimentScore'] = df['Review'].apply(lambda review: TextBlob(str(review)).sentiment.polarity)

# 標準化
df['SentimentScore'] = df['Review'].apply(lambda review: (TextBlob(str(review)).sentiment.polarity + 1) / 2)

df['SentimentScore']

df = df.reset_index(drop=True)
df

# 下載文件
from google.colab import files

df.to_csv('processed_dataset.csv', index=False)

files.download('processed_dataset.csv')

"""## gradio

### 中位數
"""

data = df

# 初始化 MinMaxScaler
scaler = MinMaxScaler()
data['NormalizedLabel'] = scaler.fit_transform(data[['Label']])

# 計算每門課程的中位數評分和平均情感分數
aggregated_data = data.groupby('CourseId').agg(
    MedianRating=('NormalizedLabel', 'median'),
    MedianSentiment=('SentimentScore', 'median')
).reset_index()

aggregated_data = aggregated_data.round({'MedianRating': 2, 'MedianSentiment': 2})

# 合併完整課程資訊
course_data = aggregated_data.merge(data[['CourseId', 'Review']], on='CourseId', how='left').drop_duplicates()

# 初始化 TF-IDF 向量化器
vectorizer = TfidfVectorizer(stop_words='english')
tfidf_matrix = vectorizer.fit_transform(course_data['Review'].fillna(''))

# 初始化翻譯模型
translator = pipeline("translation", model="Helsinki-NLP/opus-mt-zh-en")

def translate_input(user_input):
    try:
        translated_text = translator(user_input, max_length=512)[0]['translation_text']
        return translated_text
    except Exception as e:
        return user_input

def recommend_courses(user_input, model, a=0.5):
    user_input_translated = translate_input(user_input)
    user_tfidf = vectorizer.transform([user_input_translated])
    similarities = cosine_similarity(user_tfidf, tfidf_matrix).flatten()
    course_data['Similarity'] = similarities

    filtered_data = course_data[course_data['Similarity'] > 0.5].copy()
    if filtered_data.empty:
        return "抱歉，找不到與輸入相關的課程，請嘗試其他關鍵字！"

    def extract_keywords(review, top_n=3):
        tfidf = vectorizer.transform([review])
        indices = tfidf.toarray().flatten().argsort()[-top_n:][::-1]
        keywords = [vectorizer.get_feature_names_out()[i] for i in indices]
        return ', '.join(keywords)

    filtered_data['Keywords'] = filtered_data['Review'].apply(lambda x: extract_keywords(x) if pd.notnull(x) else "N/A")

    if model == "Model 1":
        result = filtered_data.sort_values(by='MedianRating', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MedianRating', 'MedianSentiment', 'Keywords']].head(10)
    elif model == "Model 2":
        result = filtered_data.sort_values(by='MeanSentiment', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MedianRating', 'MedianSentiment', 'Keywords']].head(10)
    else:
        filtered_data['Score'] = round((1-a) * filtered_data['MedianRating'] + a * filtered_data['MedianSentiment'], 2)
        result = filtered_data.sort_values(by='Score', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MedianRating', 'MedianSentiment', 'Score', 'Keywords']].head(10)

    return tabulate(result, headers='keys', tablefmt='psql', showindex=False)

def gradio_interface(user_input, model, a):
    return recommend_courses(user_input, model, a)

iface = gr.Interface(
    fn=gradio_interface,
    inputs=[
        gr.Textbox(label="請輸入想查找的課程主題（例如: Python）"),
        gr.Dropdown(choices=["Model 1", "Model 2", "Model 3"], label="選擇推薦模型"),
        gr.Slider(minimum=0, maximum=1, step=0.1, value=0.5, label="設定 a 值(針對model 3 )")
    ],
    outputs="text",
    title="coursera課程推薦系統(median)",
     description=(
        "輸入想學習的主題，選擇推薦模型，推薦相關課程: \n"
        "Model 1 - 以 rating 中位數排序\n"
        "Model 2 - 以 sentiment score 中位數排序\n"
        "Model 3 - 以綜合分數排序 (公式: rating 中位數 + a * sentiment score 中位數)")
    )

iface.launch()

"""###平均數(最後用這個)"""

df = pd.read_csv('https://github.com/yi925/coursera_course_recommend/raw/refs/heads/main/processed_dataset.csv')

data = df

nltk.download('averaged_perceptron_tagger')

# 初始化 MinMaxScaler
scaler = MinMaxScaler()
data['NormalizedLabel'] = scaler.fit_transform(data[['Label']])

# 計算每門課程的中位數評分和平均情感分數
aggregated_data = data.groupby('CourseId').agg(
    MeanRating=('NormalizedLabel', 'mean'),
    MeanSentiment=('SentimentScore', 'mean')
).reset_index()

aggregated_data = aggregated_data.round({'MeanRating': 2, 'MeanSentiment': 2})

# 合併完整課程資訊
course_data = aggregated_data.merge(data[['CourseId', 'Review']], on='CourseId', how='left').drop_duplicates()

# 初始化 TF-IDF 向量化器
vectorizer = TfidfVectorizer(stop_words='english')
tfidf_matrix = vectorizer.fit_transform(course_data['Review'].fillna(''))

# 初始化翻譯模型
translator = pipeline("translation", model="Helsinki-NLP/opus-mt-zh-en")

def translate_input(user_input):
    try:
        translated_text = translator(user_input, max_length=512)[0]['translation_text']
        return translated_text
    except Exception as e:
        return user_input

def recommend_courses(user_input, model, a=0.5):
    user_input_translated = translate_input(user_input)
    user_tfidf = vectorizer.transform([user_input_translated])
    similarities = cosine_similarity(user_tfidf, tfidf_matrix).flatten()
    course_data['Similarity'] = similarities

    filtered_data = course_data[course_data['Similarity'] > 0.5].copy()
    if filtered_data.empty:
        return "抱歉，找不到與輸入相關的課程，請嘗試其他關鍵字！"

    def extract_keywords(review, course_id, vectorizer, top_n=3):
        tfidf = vectorizer.transform([review])
        indices = tfidf.toarray().flatten().argsort()[-top_n:][::-1]
        keywords = [
        vectorizer.get_feature_names_out()[i]
        for i in indices
        if vectorizer.get_feature_names_out()[i].lower() not in course_id.lower()
        ]
        # Return the keywords as a comma-separated string
        return ', '.join(keywords) if keywords else "N/A"

    # Apply the function to the DataFrame
    filtered_data['Keywords'] = filtered_data.apply(
      lambda row: extract_keywords(row['Review'], row['CourseId'], vectorizer) if pd.notnull(row['Review']) else "N/A",
      axis=1
    )

    if model == "Model 1":
        result = filtered_data.sort_values(by='MeanRating', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MeanRating', 'MeanSentiment', 'Keywords']].head(10)
    elif model == "Model 2":
        result = filtered_data.sort_values(by='MeanSentiment', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MeanRating', 'MeanSentiment', 'Keywords']].head(10)
    else:
        filtered_data['Score'] = round((1-a) * filtered_data['MeanRating'] + a * filtered_data['MeanSentiment'], 2)
        result = filtered_data.sort_values(by='Score', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MeanRating', 'MeanSentiment', 'Score', 'Keywords']].head(10)

    return tabulate(result, headers='keys', tablefmt='psql', showindex=False)

def gradio_interface(user_input, model, a):
    return recommend_courses(user_input, model, a)

iface = gr.Interface(
    fn=gradio_interface,
    inputs=[
        gr.Textbox(label="請輸入想查找的課程主題（例如: Python）"),
        gr.Dropdown(choices=["Model 1", "Model 2", "Model 3"], label="選擇推薦模型"),
        gr.Slider(minimum=0, maximum=1, step=0.1, value=0.5, label="設定 a 值(針對model 3 )")
    ],
    outputs="text",
    title="coursera課程推薦系統",
     description=(
        "輸入想學習的主題，選擇推薦模型，推薦相關課程 : "
        )
    )

iface.launch()

df = pd.read_csv('https://github.com/yi925/coursera_course_recommend/raw/refs/heads/main/processed_dataset.csv')

data = df

# 初始化 MinMaxScaler
scaler = MinMaxScaler()
data['NormalizedLabel'] = scaler.fit_transform(data[['Label']])

# 計算每門課程的中位數評分和平均情感分數
aggregated_data = data.groupby('CourseId').agg(
    MeanRating=('NormalizedLabel', 'mean'),
    MeanSentiment=('SentimentScore', 'mean')
).reset_index()

aggregated_data = aggregated_data.round({'MeanRating': 2, 'MeanSentiment': 2})

# 合併完整課程資訊
course_data = aggregated_data.merge(data[['CourseId', 'Review']], on='CourseId', how='left').drop_duplicates()

# 初始化 TF-IDF 向量化器
vectorizer = TfidfVectorizer(stop_words='english')
tfidf_matrix = vectorizer.fit_transform(course_data['Review'].fillna(''))

# 初始化翻譯模型
translator = pipeline("translation", model="Helsinki-NLP/opus-mt-zh-en")

def translate_input(user_input):
    try:
        translated_text = translator(user_input, max_length=512)[0]['translation_text']
        return translated_text
    except Exception as e:
        return user_input

import nltk
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')

def extract_adjective_keywords(review, top_n=3):   #關鍵字不要出現跟課程名稱相同的詞
    # 如果評論為空，返回 "N/A"
    if pd.isnull(review):
        return "N/A"

    # 分詞
    words = nltk.word_tokenize(review)

    # 詞性標注
    pos_tags = nltk.pos_tag(words)

    # 篩選形容詞 (JJ: 形容詞, JJR: 比較級形容詞, JJS: 最高級形容詞)
    adjectives = [word for word, pos in pos_tags if pos in ['JJ', 'JJR', 'JJS']]

    # 如果沒有形容詞，返回 "N/A"
    if not adjectives:
        return "N/A"

    # 使用 TF-IDF 權重排序形容詞
    tfidf_matrix = vectorizer.transform(adjectives)
    tfidf_scores = tfidf_matrix.toarray().flatten()

    # 取出 top_n 個形容詞
    top_indices = tfidf_scores.argsort()[-top_n:][::-1]
    top_adjectives = [adjectives[i] for i in top_indices]

    return ', '.join(top_adjectives)

    # 應用到數據集
    filtered_data['Keywords'] = filtered_data['Review'].apply(extract_adjective_keywords)

    if model == "Model 1":
        result = filtered_data.sort_values(by='MeanRating', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MeanRating', 'MeanSentiment', 'Keywords']].head(10)
    elif model == "Model 2":
        result = filtered_data.sort_values(by='MeanSentiment', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MeanRating', 'MeanSentiment', 'Keywords']].head(10)
    else:
        filtered_data['Score'] = round((1-a) * filtered_data['MeanRating'] + a * filtered_data['MeanSentiment'], 2)
        result = filtered_data.sort_values(by='Score', ascending=False).drop_duplicates(subset='CourseId')
        result = result[['CourseId', 'MeanRating', 'MeanSentiment', 'Score', 'Keywords']].head(10)

    return tabulate(result, headers='keys', tablefmt='psql', showindex=False)

def gradio_interface(user_input, model, a):
    return recommend_courses(user_input, model, a)

iface = gr.Interface(
    fn=gradio_interface,
    inputs=[
        gr.Textbox(label="請輸入想查找的課程主題（例如: Python）"),
        gr.Dropdown(choices=["Model 1", "Model 2", "Model 3"], label="選擇推薦模型"),
        gr.Slider(minimum=0, maximum=1, step=0.1, value=0.5, label="設定 a 值(針對model 3 )")
    ],
    outputs="text",
    title="coursera課程推薦系統(mean)",
     description=(
        "輸入想學習的主題，選擇推薦模型，推薦相關課程 : "
        "Model 1 - 以 rating 平均數排序/"
        "Model 2 - 以 sentiment score 平均數排序/"
        "Model 3 - 以綜合分數排序 (公式: rating 平均數 + a * sentiment score 平均數)")
    )

iface.launch()

"""### 印出全部model"""

# Gradio 介面
def gradio_interface(user_input, a=0.5):
    return recommend_courses(user_input, a)


interface = gr.Interface(
    fn=gradio_interface,
    inputs=[
        gr.Textbox(label="請輸入您的需求（例如：想學 Python）"),
        gr.Slider(label="自定參數 a", minimum=0, maximum=1, step=0.1, value=0.5)
    ],
    outputs=[
        gr.Textbox(label="模型 1 - 按平均數評分排序"),
        gr.Textbox(label="模型 2 - 按平均數情感分數排序"),
        gr.Textbox(label="模型 3 - 自定公式排序")
    ],
    title="課程推薦系統",
    description="輸入您的需求，推薦相關課程。"
)


interface.launch()