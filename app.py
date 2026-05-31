# -*- coding: utf-8 -*-
"""
قراءة الخريطة الشخصية - V6.0 Railway Final

ما الجديد في V1.2:
- لم يعد التطبيق محصورًا بعدد قليل من الدول.
- يستخدم geonamescache لجلب دول ومدن العالم تقريبًا.
- المستخدم يختار الدولة ثم يكتب اسم المدينة.
- خط العرض وخط الطول وفرق التوقيت تبقى مخفية عن القارئ.
- الساعة بنظام 24 ساعة بوضوح.

المتطلبات:
pip install flask pyswisseph geonamescache

طريقة التشغيل:
python personal_chart_reader_v1_2.py

ثم افتح:
http://127.0.0.1:5000
"""

from __future__ import annotations

import math
import json
import os
import sys
import urllib.request
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from flask import Flask, request, render_template_string, jsonify, session, redirect, url_for

try:
    import swisseph as swe
    SWISSEPH_AVAILABLE = True
except Exception:
    swe = None
    SWISSEPH_AVAILABLE = False


def setup_swiss_ephemeris_path():
    """
    يحاول ضبط مسارات ملفات Swiss Ephemeris تلقائيًا.
    هذا مهم لحساب الكويكبات مثل كايرون، جونو، فيستا، بالاس، سيريس، فولو.
    إذا لم توجد ملفات مثل seas_18.se1 فلن تستطيع pyswisseph حساب هذه الكويكبات.
    """
    if not SWISSEPH_AVAILABLE:
        return

    candidate_paths = []

    # مجلد بجانب ملف التطبيق
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_paths.append(script_dir)
        candidate_paths.append(os.path.join(script_dir, "sweph"))
        candidate_paths.append(os.path.join(script_dir, "ephe"))
        candidate_paths.append(os.path.join(script_dir, "swisseph"))
    except Exception:
        pass

    # مسارات شائعة على أندرويد / Pydroid
    candidate_paths.extend([
        "/storage/emulated/0/sweph",
        "/storage/emulated/0/Download/sweph",
        "/storage/emulated/0/Pydroid3/sweph",
        "/sdcard/sweph",
        "/sdcard/Download/sweph",
    ])

    # إذا كانت kerykeion مثبتة، غالبًا تحتوي ملفات ephemeris
    try:
        import kerykeion
        kery_path = os.path.dirname(os.path.abspath(kerykeion.__file__))
        candidate_paths.append(os.path.join(kery_path, "sweph"))
    except Exception:
        pass

    # مسارات Linux شائعة
    candidate_paths.extend([
        "/usr/share/swisseph",
        "/usr/local/share/swisseph",
        "/opt/pyvenv/lib/python3.13/site-packages/kerykeion/sweph",
        "/opt/pyvenv/lib64/python3.13/site-packages/kerykeion/sweph",
    ])

    # اختر المسارات الموجودة فقط
    existing = []
    for p in candidate_paths:
        try:
            if p and os.path.isdir(p) and p not in existing:
                existing.append(p)
        except Exception:
            pass

    if existing:
        try:
            swe.set_ephe_path(os.pathsep.join(existing))
        except Exception:
            pass


setup_swiss_ephemeris_path()


ASTEROID_EPHEMERIS_FILENAME = "seas_18.se1"

ASTEROID_EPHEMERIS_URLS = [
    "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/seas_18.se1",
    "https://raw.githubusercontent.com/chapagain/php-swiss-ephemeris/master/sweph/seas_18.se1",
]


def candidate_sweph_dirs() -> List[str]:
    dirs: List[str] = []

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs.extend([
            script_dir,
            os.path.join(script_dir, "sweph"),
            os.path.join(script_dir, "ephe"),
            os.path.join(script_dir, "swisseph"),
        ])
    except Exception:
        pass

    dirs.extend([
        "/storage/emulated/0/sweph",
        "/storage/emulated/0/Download/sweph",
        "/storage/emulated/0/Pydroid3/sweph",
        "/sdcard/sweph",
        "/sdcard/Download/sweph",
    ])

    try:
        import kerykeion
        kery_path = os.path.dirname(os.path.abspath(kerykeion.__file__))
        dirs.append(os.path.join(kery_path, "sweph"))
    except Exception:
        pass

    clean: List[str] = []
    for d in dirs:
        if d and d not in clean:
            clean.append(d)
    return clean


def find_asteroid_ephemeris_file() -> str:
    for d in candidate_sweph_dirs():
        try:
            f = os.path.join(d, ASTEROID_EPHEMERIS_FILENAME)
            if os.path.isfile(f) and os.path.getsize(f) > 100000:
                return f
        except Exception:
            continue
    return ""


def writable_sweph_dir() -> str:
    for d in candidate_sweph_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, ".write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(test_file)
            except Exception:
                pass
            return d
        except Exception:
            continue
    return ""


def download_asteroid_ephemeris_file() -> str:
    existing = find_asteroid_ephemeris_file()
    if existing:
        return existing

    target_dir = writable_sweph_dir()
    if not target_dir:
        return ""

    target_file = os.path.join(target_dir, ASTEROID_EPHEMERIS_FILENAME)

    for url in ASTEROID_EPHEMERIS_URLS:
        try:
            urllib.request.urlretrieve(url, target_file)
            if os.path.isfile(target_file) and os.path.getsize(target_file) > 100000:
                try:
                    swe.set_ephe_path(target_dir)
                except Exception:
                    pass
                setup_swiss_ephemeris_path()
                return target_file
        except Exception:
            try:
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(url, timeout=25, context=ctx) as response:
                    data = response.read()
                if len(data) > 100000:
                    with open(target_file, "wb") as f:
                        f.write(data)
                    try:
                        swe.set_ephe_path(target_dir)
                    except Exception:
                        pass
                    setup_swiss_ephemeris_path()
                    return target_file
            except Exception:
                continue

    return ""


def ensure_asteroid_ephemeris_ready() -> bool:
    if not SWISSEPH_AVAILABLE:
        return False

    existing = find_asteroid_ephemeris_file()
    if existing:
        try:
            swe.set_ephe_path(os.path.dirname(existing))
        except Exception:
            setup_swiss_ephemeris_path()
        return True

    downloaded = download_asteroid_ephemeris_file()
    if downloaded:
        try:
            swe.set_ephe_path(os.path.dirname(downloaded))
        except Exception:
            setup_swiss_ephemeris_path()
        return True

    return False


try:
    import geonamescache
    GEONAMESCACHE_AVAILABLE = True
except Exception:
    geonamescache = None
    GEONAMESCACHE_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except Exception:
    ZoneInfo = None
    ZONEINFO_AVAILABLE = False


# ============================================================
# إعدادات عامة
# ============================================================

APP_TITLE = "قراءة الخريطة الشخصية"

SIGNS_AR = [
    "الحمل", "الثور", "الجوزاء", "السرطان",
    "الأسد", "العذراء", "الميزان", "العقرب",
    "القوس", "الجدي", "الدلو", "الحوت"
]

PLANETS = {
    "Sun": {"ar": "الشمس", "id": 0},
    "Moon": {"ar": "القمر", "id": 1},
    "Mercury": {"ar": "عطارد", "id": 2},
    "Venus": {"ar": "الزهرة", "id": 3},
    "Mars": {"ar": "المريخ", "id": 4},
    "Jupiter": {"ar": "المشتري", "id": 5},
    "Saturn": {"ar": "زحل", "id": 6},
    "Uranus": {"ar": "أورانوس", "id": 7},
    "Neptune": {"ar": "نبتون", "id": 8},
    "Pluto": {"ar": "بلوتو", "id": 9},
}

SIGN_RULERS = {
    "الحمل": "المريخ",
    "الثور": "الزهرة",
    "الجوزاء": "عطارد",
    "السرطان": "القمر",
    "الأسد": "الشمس",
    "العذراء": "عطارد",
    "الميزان": "الزهرة",
    "العقرب": "المريخ",
    "القوس": "المشتري",
    "الجدي": "زحل",
    "الدلو": "زحل",
    "الحوت": "المشتري",
}

ELEMENTS = {
    "الحمل": "نار", "الأسد": "نار", "القوس": "نار",
    "الثور": "تراب", "العذراء": "تراب", "الجدي": "تراب",
    "الجوزاء": "هواء", "الميزان": "هواء", "الدلو": "هواء",
    "السرطان": "ماء", "العقرب": "ماء", "الحوت": "ماء",
}

PTOLEMY_TERMS = {
    "الحمل": [(6, "المشتري"), (12, "الزهرة"), (20, "عطارد"), (25, "المريخ"), (30, "زحل")],
    "الثور": [(8, "الزهرة"), (15, "عطارد"), (22, "المشتري"), (27, "زحل"), (30, "المريخ")],
    "الجوزاء": [(6, "عطارد"), (12, "المشتري"), (17, "الزهرة"), (24, "المريخ"), (30, "زحل")],
    "السرطان": [(7, "المريخ"), (13, "الزهرة"), (19, "عطارد"), (26, "المشتري"), (30, "زحل")],
    "الأسد": [(6, "زحل"), (13, "عطارد"), (19, "الزهرة"), (25, "المشتري"), (30, "المريخ")],
    "العذراء": [(7, "عطارد"), (13, "الزهرة"), (17, "المشتري"), (21, "المريخ"), (30, "زحل")],
    "الميزان": [(6, "زحل"), (14, "عطارد"), (21, "المشتري"), (28, "الزهرة"), (30, "المريخ")],
    "العقرب": [(7, "المريخ"), (11, "الزهرة"), (19, "عطارد"), (24, "المشتري"), (30, "زحل")],
    "القوس": [(12, "المشتري"), (17, "الزهرة"), (21, "عطارد"), (26, "زحل"), (30, "المريخ")],
    "الجدي": [(7, "عطارد"), (14, "المشتري"), (22, "الزهرة"), (26, "زحل"), (30, "المريخ")],
    "الدلو": [(7, "عطارد"), (13, "الزهرة"), (20, "المشتري"), (25, "المريخ"), (30, "زحل")],
    "الحوت": [(12, "الزهرة"), (16, "المشتري"), (19, "عطارد"), (28, "المريخ"), (30, "زحل")],
}

# بدائل عربية شائعة لبعض الدول والمدن لتسهيل الاستخدام.
COUNTRY_AR_NAMES = {
    "Iraq": "العراق",
    "Saudi Arabia": "السعودية",
    "Kuwait": "الكويت",
    "Jordan": "الأردن",
    "Egypt": "مصر",
    "United Arab Emirates": "الإمارات",
    "Qatar": "قطر",
    "Bahrain": "البحرين",
    "Oman": "عُمان",
    "Yemen": "اليمن",
    "Syria": "سوريا",
    "Lebanon": "لبنان",
    "Turkey": "تركيا",
    "Iran": "إيران",
    "United States": "الولايات المتحدة",
    "United Kingdom": "بريطانيا",
    "Germany": "ألمانيا",
    "France": "فرنسا",
    "Canada": "كندا",
    "Australia": "أستراليا",
}

# قاموس عربي داخلي للمدن المهمة.
# هذا القاموس لا يحصر التطبيق، بل يساعده على فهم الاسم العربي مباشرة.
# إذا لم يجد المدينة هنا، ينتقل إلى geonamescache للبحث العالمي.
CITY_AR_OVERRIDES = {
    "IQ": {
        "بغداد": {"name": "", "lat": 33.3152, "lon": 44.3661, "timezone": "Asia/Baghdad"},
        "النجف": {"name": "", "lat": 32.0000, "lon": 44.3333, "timezone": "Asia/Baghdad"},
        "نجف": {"name": "", "lat": 32.0000, "lon": 44.3333, "timezone": "Asia/Baghdad"},
        "كربلاء": {"name": "", "lat": 32.6160, "lon": 44.0249, "timezone": "Asia/Baghdad"},
        "الديوانية": {"name": "", "lat": 31.9860, "lon": 44.9250, "timezone": "Asia/Baghdad"},
        "ديوانية": {"name": "", "lat": 31.9860, "lon": 44.9250, "timezone": "Asia/Baghdad"},
        "الشامية": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "شامية": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash Shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash shamiyh": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash shamiya": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Al Shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "al shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "الكوفة": {"name": "", "lat": 32.0347, "lon": 44.4033, "timezone": "Asia/Baghdad"},
        "كوفة": {"name": "", "lat": 32.0347, "lon": 44.4033, "timezone": "Asia/Baghdad"},
        "الحلة": {"name": "", "lat": 32.4721, "lon": 44.4217, "timezone": "Asia/Baghdad"},
        "حلة": {"name": "", "lat": 32.4721, "lon": 44.4217, "timezone": "Asia/Baghdad"},
        "البصرة": {"name": "", "lat": 30.5085, "lon": 47.7804, "timezone": "Asia/Baghdad"},
        "بصرة": {"name": "", "lat": 30.5085, "lon": 47.7804, "timezone": "Asia/Baghdad"},
        "الموصل": {"name": "", "lat": 36.3489, "lon": 43.1577, "timezone": "Asia/Baghdad"},
        "موصل": {"name": "", "lat": 36.3489, "lon": 43.1577, "timezone": "Asia/Baghdad"},
        "كركوك": {"name": "", "lat": 35.4681, "lon": 44.3922, "timezone": "Asia/Baghdad"},
        "أربيل": {"name": "", "lat": 36.1911, "lon": 44.0092, "timezone": "Asia/Baghdad"},
        "اربيل": {"name": "", "lat": 36.1911, "lon": 44.0092, "timezone": "Asia/Baghdad"},
        "هولير": {"name": "", "lat": 36.1911, "lon": 44.0092, "timezone": "Asia/Baghdad"},
        "السليمانية": {"name": "", "lat": 35.5570, "lon": 45.4356, "timezone": "Asia/Baghdad"},
        "سليمانية": {"name": "", "lat": 35.5570, "lon": 45.4356, "timezone": "Asia/Baghdad"},
        "الناصرية": {"name": "", "lat": 31.0576, "lon": 46.2573, "timezone": "Asia/Baghdad"},
        "ناصرية": {"name": "", "lat": 31.0576, "lon": 46.2573, "timezone": "Asia/Baghdad"},
        "العمارة": {"name": "", "lat": 31.8356, "lon": 47.1448, "timezone": "Asia/Baghdad"},
        "عمارة": {"name": "", "lat": 31.8356, "lon": 47.1448, "timezone": "Asia/Baghdad"},
        "السماوة": {"name": "", "lat": 31.3180, "lon": 45.2803, "timezone": "Asia/Baghdad"},
        "سماوة": {"name": "", "lat": 31.3180, "lon": 45.2803, "timezone": "Asia/Baghdad"},
        "الكوت": {"name": "", "lat": 32.5147, "lon": 45.8190, "timezone": "Asia/Baghdad"},
        "كوت": {"name": "", "lat": 32.5147, "lon": 45.8190, "timezone": "Asia/Baghdad"},
        "بعقوبة": {"name": "", "lat": 33.7485, "lon": 44.6555, "timezone": "Asia/Baghdad"},
        "ديالى": {"name": "", "lat": 33.7485, "lon": 44.6555, "timezone": "Asia/Baghdad"},
        "تكريت": {"name": "", "lat": 34.6071, "lon": 43.6782, "timezone": "Asia/Baghdad"},
        "دهوك": {"name": "", "lat": 36.8667, "lon": 42.9833, "timezone": "Asia/Baghdad"},
        "الرمادي": {"name": "", "lat": 33.4206, "lon": 43.3078, "timezone": "Asia/Baghdad"},
        "رمادي": {"name": "", "lat": 33.4206, "lon": 43.3078, "timezone": "Asia/Baghdad"},
        "الفلوجة": {"name": "", "lat": 33.3558, "lon": 43.7861, "timezone": "Asia/Baghdad"},
        "فلوجة": {"name": "", "lat": 33.3558, "lon": 43.7861, "timezone": "Asia/Baghdad"},
        "سامراء": {"name": "", "lat": 34.1959, "lon": 43.8857, "timezone": "Asia/Baghdad"},
        "الزبير": {"name": "", "lat": 30.3921, "lon": 47.7018, "timezone": "Asia/Baghdad"},
        "زبير": {"name": "", "lat": 30.3921, "lon": 47.7018, "timezone": "Asia/Baghdad"},
        "القائم": {"name": "", "lat": 34.3686, "lon": 41.0945, "timezone": "Asia/Baghdad"},
        "هيت": {"name": "", "lat": 33.6416, "lon": 42.8251, "timezone": "Asia/Baghdad"},
        "عفك": {"name": "", "lat": 32.0643, "lon": 45.2474, "timezone": "Asia/Baghdad"},
        "الحمزة": {"name": "", "lat": 31.7330, "lon": 44.6600, "timezone": "Asia/Baghdad"},
    },
    "SA": {
        "الرياض": {"name": "", "lat": 24.7136, "lon": 46.6753, "timezone": "Asia/Riyadh"},
        "جدة": {"name": "", "lat": 21.4858, "lon": 39.1925, "timezone": "Asia/Riyadh"},
        "مكة": {"name": "", "lat": 21.3891, "lon": 39.8579, "timezone": "Asia/Riyadh"},
        "مكة المكرمة": {"name": "", "lat": 21.3891, "lon": 39.8579, "timezone": "Asia/Riyadh"},
        "المدينة": {"name": "", "lat": 24.5247, "lon": 39.5692, "timezone": "Asia/Riyadh"},
        "المدينة المنورة": {"name": "", "lat": 24.5247, "lon": 39.5692, "timezone": "Asia/Riyadh"},
        "الدمام": {"name": "", "lat": 26.4207, "lon": 50.0888, "timezone": "Asia/Riyadh"},
        "الخبر": {"name": "", "lat": 26.2172, "lon": 50.1971, "timezone": "Asia/Riyadh"},
        "الطائف": {"name": "", "lat": 21.4373, "lon": 40.5127, "timezone": "Asia/Riyadh"},
        "تبوك": {"name": "", "lat": 28.3838, "lon": 36.5662, "timezone": "Asia/Riyadh"},
        "أبها": {"name": "", "lat": 18.2164, "lon": 42.5053, "timezone": "Asia/Riyadh"},
        "ابها": {"name": "", "lat": 18.2164, "lon": 42.5053, "timezone": "Asia/Riyadh"},
        "بريدة": {"name": "", "lat": 26.3592, "lon": 43.9818, "timezone": "Asia/Riyadh"},
        "حائل": {"name": "", "lat": 27.5114, "lon": 41.7208, "timezone": "Asia/Riyadh"},
        "جازان": {"name": "", "lat": 16.8892, "lon": 42.5511, "timezone": "Asia/Riyadh"},
    },
    "KW": {
        "الكويت": {"name": "", "lat": 29.3759, "lon": 47.9774, "timezone": "Asia/Kuwait"},
        "مدينة الكويت": {"name": "", "lat": 29.3759, "lon": 47.9774, "timezone": "Asia/Kuwait"},
    },
    "JO": {
        "عمان": {"name": "", "lat": 31.9539, "lon": 35.9106, "timezone": "Asia/Amman"},
        "عمّان": {"name": "", "lat": 31.9539, "lon": 35.9106, "timezone": "Asia/Amman"},
        "إربد": {"name": "", "lat": 32.5556, "lon": 35.8500, "timezone": "Asia/Amman"},
        "اربد": {"name": "", "lat": 32.5556, "lon": 35.8500, "timezone": "Asia/Amman"},
        "الزرقاء": {"name": "", "lat": 32.0728, "lon": 36.0870, "timezone": "Asia/Amman"},
        "العقبة": {"name": "", "lat": 29.5267, "lon": 35.0078, "timezone": "Asia/Amman"},
    },
    "EG": {
        "القاهرة": {"name": "", "lat": 30.0444, "lon": 31.2357, "timezone": "Africa/Cairo"},
        "الجيزة": {"name": "", "lat": 30.0131, "lon": 31.2089, "timezone": "Africa/Cairo"},
        "الإسكندرية": {"name": "", "lat": 31.2001, "lon": 29.9187, "timezone": "Africa/Cairo"},
        "الاسكندرية": {"name": "", "lat": 31.2001, "lon": 29.9187, "timezone": "Africa/Cairo"},
        "الأقصر": {"name": "", "lat": 25.6872, "lon": 32.6396, "timezone": "Africa/Cairo"},
        "الاقصر": {"name": "", "lat": 25.6872, "lon": 32.6396, "timezone": "Africa/Cairo"},
        "أسوان": {"name": "", "lat": 24.0889, "lon": 32.8998, "timezone": "Africa/Cairo"},
        "اسوان": {"name": "", "lat": 24.0889, "lon": 32.8998, "timezone": "Africa/Cairo"},
        "المنصورة": {"name": "", "lat": 31.0409, "lon": 31.3785, "timezone": "Africa/Cairo"},
        "طنطا": {"name": "", "lat": 30.7865, "lon": 31.0004, "timezone": "Africa/Cairo"},
        "بورسعيد": {"name": "", "lat": 31.2653, "lon": 32.3019, "timezone": "Africa/Cairo"},
        "السويس": {"name": "", "lat": 29.9668, "lon": 32.5498, "timezone": "Africa/Cairo"},
    },
    "AE": {
        "دبي": {"name": "", "lat": 25.2048, "lon": 55.2708, "timezone": "Asia/Dubai"},
        "أبوظبي": {"name": "", "lat": 24.4539, "lon": 54.3773, "timezone": "Asia/Dubai"},
        "ابوظبي": {"name": "", "lat": 24.4539, "lon": 54.3773, "timezone": "Asia/Dubai"},
        "الشارقة": {"name": "", "lat": 25.3463, "lon": 55.4209, "timezone": "Asia/Dubai"},
        "العين": {"name": "", "lat": 24.2075, "lon": 55.7447, "timezone": "Asia/Dubai"},
        "عجمان": {"name": "", "lat": 25.4052, "lon": 55.5136, "timezone": "Asia/Dubai"},
        "رأس الخيمة": {"name": "", "lat": 25.7895, "lon": 55.9432, "timezone": "Asia/Dubai"},
        "راس الخيمة": {"name": "", "lat": 25.7895, "lon": 55.9432, "timezone": "Asia/Dubai"},
    },
    "QA": {
        "الدوحة": {"name": "", "lat": 25.2854, "lon": 51.5310, "timezone": "Asia/Qatar"},
        "دوحة": {"name": "", "lat": 25.2854, "lon": 51.5310, "timezone": "Asia/Qatar"},
    },
    "BH": {
        "المنامة": {"name": "", "lat": 26.2235, "lon": 50.5876, "timezone": "Asia/Bahrain"},
        "منامة": {"name": "", "lat": 26.2235, "lon": 50.5876, "timezone": "Asia/Bahrain"},
    },
    "OM": {
        "مسقط": {"name": "", "lat": 23.5880, "lon": 58.3829, "timezone": "Asia/Muscat"},
        "صلالة": {"name": "", "lat": 17.0194, "lon": 54.1108, "timezone": "Asia/Muscat"},
    },
    "YE": {
        "صنعاء": {"name": "", "lat": 15.3694, "lon": 44.1910, "timezone": "Asia/Aden"},
        "عدن": {"name": "", "lat": 12.7855, "lon": 45.0187, "timezone": "Asia/Aden"},
        "تعز": {"name": "", "lat": 13.5795, "lon": 44.0209, "timezone": "Asia/Aden"},
    },
    "SY": {
        "دمشق": {"name": "", "lat": 33.5138, "lon": 36.2765, "timezone": "Asia/Damascus"},
        "حلب": {"name": "", "lat": 36.2021, "lon": 37.1343, "timezone": "Asia/Damascus"},
        "حمص": {"name": "", "lat": 34.7324, "lon": 36.7137, "timezone": "Asia/Damascus"},
        "حماة": {"name": "", "lat": 35.1318, "lon": 36.7578, "timezone": "Asia/Damascus"},
        "اللاذقية": {"name": "", "lat": 35.5317, "lon": 35.7901, "timezone": "Asia/Damascus"},
        "اللاذقيه": {"name": "", "lat": 35.5317, "lon": 35.7901, "timezone": "Asia/Damascus"},
    },
    "LB": {
        "بيروت": {"name": "", "lat": 33.8938, "lon": 35.5018, "timezone": "Asia/Beirut"},
        "طرابلس": {"name": "", "lat": 34.4367, "lon": 35.8497, "timezone": "Asia/Beirut"},
        "صيدا": {"name": "", "lat": 33.5571, "lon": 35.3715, "timezone": "Asia/Beirut"},
        "صور": {"name": "", "lat": 33.2704, "lon": 35.2038, "timezone": "Asia/Beirut"},
    },
    "TR": {
        "اسطنبول": {"name": "", "lat": 41.0082, "lon": 28.9784, "timezone": "Europe/Istanbul"},
        "إسطنبول": {"name": "", "lat": 41.0082, "lon": 28.9784, "timezone": "Europe/Istanbul"},
        "انقرة": {"name": "", "lat": 39.9334, "lon": 32.8597, "timezone": "Europe/Istanbul"},
        "أنقرة": {"name": "", "lat": 39.9334, "lon": 32.8597, "timezone": "Europe/Istanbul"},
        "ازمير": {"name": "", "lat": 38.4237, "lon": 27.1428, "timezone": "Europe/Istanbul"},
        "إزمير": {"name": "", "lat": 38.4237, "lon": 27.1428, "timezone": "Europe/Istanbul"},
        "اورفا": {"name": "", "lat": 37.1674, "lon": 38.7955, "timezone": "Europe/Istanbul"},
        "أورفا": {"name": "", "lat": 37.1674, "lon": 38.7955, "timezone": "Europe/Istanbul"},
    },
    "IR": {
        "طهران": {"name": "", "lat": 35.6892, "lon": 51.3890, "timezone": "Asia/Tehran"},
        "مشهد": {"name": "", "lat": 36.2605, "lon": 59.6168, "timezone": "Asia/Tehran"},
        "قم": {"name": "", "lat": 34.6416, "lon": 50.8746, "timezone": "Asia/Tehran"},
        "اصفهان": {"name": "", "lat": 32.6546, "lon": 51.6680, "timezone": "Asia/Tehran"},
        "أصفهان": {"name": "", "lat": 32.6546, "lon": 51.6680, "timezone": "Asia/Tehran"},
        "شيراز": {"name": "", "lat": 29.5918, "lon": 52.5837, "timezone": "Asia/Tehran"},
    },
}

# أسماء بديلة تستخدم في البحث داخل geonamescache إذا لم تكن المدينة في القاموس أعلاه.
CITY_ALIASES = {
    "بغداد": ["Baghdad"],
    "النجف": ["Najaf", "An Najaf"],
    "كربلاء": ["Karbala", "Karbala'"],
    "الديوانية": ["Ad Diwaniyah", "Diwaniyah"],
    "الشامية": ["Ash Shamiyah", "Ash Shāmīyah"],
    "البصرة": ["Basra", "Al Basrah"],
    "الموصل": ["Mosul", "Al Mawsil"],
    "كركوك": ["Kirkuk"],
    "أربيل": ["Erbil", "Arbil"],
    "اربيل": ["Erbil", "Arbil"],
    "السليمانية": ["Sulaymaniyah", "As Sulaymaniyah"],
    "الناصرية": ["Nasiriyah", "An Nasiriyah"],
    "الحلة": ["Al Hillah", "Hillah"],
    "الرمادي": ["Ramadi", "Ar Ramadi"],
    "العمارة": ["Amarah", "Al Amarah"],
    "السماوة": ["Samawah", "As Samawah"],
    "الكوت": ["Kut", "Al Kut"],
    "بعقوبة": ["Baqubah"],
    "تكريت": ["Tikrit"],
    "دهوك": ["Duhok", "Dihok"],
    "الرياض": ["Riyadh"],
    "جدة": ["Jeddah"],
    "مكة": ["Mecca", "Makkah"],
    "المدينة": ["Medina"],
    "القاهرة": ["Cairo"],
    "الإسكندرية": ["Alexandria"],
    "دبي": ["Dubai"],
    "أبوظبي": ["Abu Dhabi"],
    "عمّان": ["Amman"],
    "عمان": ["Amman", "Muscat"],
}


@dataclass
class BodyPosition:
    name_en: str
    name_ar: str
    lon: float
    sign: str
    degree: float
    house: Optional[int] = None
    term: Optional[str] = None
    retrograde: bool = False


# ============================================================
# قاعدة المدن العالمية
# ============================================================

def build_country_list() -> List[Dict[str, str]]:
    """
    ترجع قائمة الدول أبجديًا كما هي، مع ضمان وجود العراق داخل موضعه الطبيعي.
    لا يتم تثبيت العراق في الأعلى؛ فقط نضمن عدم اختفائه من القائمة.
    """
    items: List[Dict[str, str]] = []

    if GEONAMESCACHE_AVAILABLE:
        gc = geonamescache.GeonamesCache()
        countries = gc.get_countries()

        for code, info in countries.items():
            en_name = info.get("name", code)

            # نترك القائمة أبجدية إنكليزية واضحة للمستخدم،
            # ونظهر العراق باسم مزدوج حتى يكون سهل العثور عليه.
            if code == "IQ":
                display = "Iraq / العراق"
            else:
                display = COUNTRY_AR_NAMES.get(en_name, en_name)

            items.append({"code": code, "name": display})

    # ضمان العراق حتى إذا لم يرجعه مصدر الدول لأي سبب
    if not any(item.get("code") == "IQ" for item in items):
        items.append({"code": "IQ", "name": "Iraq / العراق"})

    # ترتيب أبجدي طبيعي حسب الاسم الظاهر
    items.sort(key=lambda x: x["name"])
    return items


def get_city_candidates(country_code: str) -> List[Dict[str, object]]:
    """
    يرجع مدن الدولة من geonamescache.
    نأخذ المدن الأكثر شهرة أولًا حسب عدد السكان.
    """
    if not GEONAMESCACHE_AVAILABLE:
        return [
            {"name": "", "display": "Baghdad", "lat": 33.3152, "lon": 44.3661, "timezone": "Asia/Baghdad", "population": 0}
        ]

    gc = geonamescache.GeonamesCache()
    cities = gc.get_cities()

    result = []
    for _, c in cities.items():
        if c.get("countrycode") != country_code:
            continue

        name = c.get("name", "")
        lat = float(c.get("latitude", 0.0))
        lon = float(c.get("longitude", 0.0))
        timezone = c.get("timezone", "")
        population = int(c.get("population", 0) or 0)

        result.append({
            "name": name,
            "display": name,
            "lat": lat,
            "lon": lon,
            "timezone": timezone,
            "population": population,
        })

    result.sort(key=lambda x: int(x.get("population", 0)), reverse=True)
    return result


def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ى": "ي", "ة": "ه",
        "’": "'", "‘": "'", "`": "'",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    return s


def find_city(country_code: str, city_input: str) -> Optional[Dict[str, object]]:
    """
    يبحث عن المدينة داخل الدولة.
    يقبل الاسم الإنجليزي الموجود في geonamescache،
    ويقبل بعض الأسماء العربية الشائعة عبر CITY_ALIASES.
    """
    city_input = (city_input or "").strip()
    if not city_input:
        return None

    # 1) البحث أولًا في القاموس العربي الداخلي.
    normalized_input = normalize_text(city_input)
    overrides = CITY_AR_OVERRIDES.get(country_code, {})
    for ar_name, info in overrides.items():
        if normalize_text(ar_name) == normalized_input:
            return {
                "name": info["name"],
                "display": ar_name,
                "lat": float(info["lat"]),
                "lon": float(info["lon"]),
                "timezone": info["timezone"],
                "population": 0,
            }

    candidates = get_city_candidates(country_code)
    wanted_norm = normalize_text(city_input)

    # تحويل الاسم العربي إلى احتمالات إنجليزية إن وجد.
    search_names = [city_input]
    if city_input in CITY_ALIASES:
        search_names.extend(CITY_ALIASES[city_input])

    normalized_search = [normalize_text(x) for x in search_names]

    # تطابق كامل
    for c in candidates:
        c_norm = normalize_text(str(c["name"]))
        if c_norm in normalized_search:
            return c

    # يبدأ بنفس الاسم
    for c in candidates:
        c_norm = normalize_text(str(c["name"]))
        if any(c_norm.startswith(s) or s.startswith(c_norm) for s in normalized_search if s):
            return c

    # يحتوي الاسم
    for c in candidates:
        c_norm = normalize_text(str(c["name"]))
        if any(s in c_norm or c_norm in s for s in normalized_search if len(s) >= 3):
            return c

    return None


def timezone_offset_for_birth(tz_name: str, year: int, month: int, day: int, hour: int, minute: int) -> float:
    """
    يحسب فرق التوقيت من اسم المنطقة الزمنية إذا أمكن.
    إن لم يتوفر zoneinfo أو اسم المنطقة، يرجع 3 كافتراضي للعراق.
    """
    if not tz_name or not ZONEINFO_AVAILABLE:
        return 3.0

    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz_name))
        offset = dt.utcoffset()
        if offset is None:
            return 3.0
        return offset.total_seconds() / 3600.0
    except Exception:
        return 3.0


def city_suggestions_for_country(country_code: str, limit: int = 120) -> List[str]:
    suggestions: List[str] = []

    # نضع أسماء المدن العربية في البداية إن كانت موجودة في القاموس.
    for ar_name in CITY_AR_OVERRIDES.get(country_code, {}).keys():
        if ar_name not in suggestions:
            suggestions.append(ar_name)

    # ترتيب خاص للعراق حتى تظهر المدن المطلوبة بوضوح في أول القائمة.
    if country_code == "IQ":
        priority = [
            "بغداد", "النجف", "كربلاء", "الديوانية", "الشامية", "البصرة",
            "الموصل", "كركوك", "أربيل", "السليمانية", "الناصرية", "الحلة",
            "الرمادي", "العمارة", "السماوة", "الكوت", "بعقوبة", "تكريت",
            "دهوك", "الفلوجة", "سامراء"
        ]
        ordered = []
        for x in priority + suggestions:
            if x not in ordered:
                ordered.append(x)
        suggestions = ordered

    # ثم نضيف أشهر المدن العالمية من geonamescache.
    cities = get_city_candidates(country_code)
    for c in cities[:limit]:
        name = str(c["name"])
        if name not in suggestions:
            suggestions.append(name)

    return suggestions[:limit + 120]


# ============================================================
# أدوات حسابية
# ============================================================

def normalize_deg(x: float) -> float:
    return x % 360.0


def sign_from_lon(lon: float) -> Tuple[str, float]:
    lon = normalize_deg(lon)
    idx = int(lon // 30)
    sign = SIGNS_AR[idx]
    degree = lon - idx * 30
    return sign, degree


def format_degree(deg: float) -> str:
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d:02d}°{m:02d}′"


def angular_distance(a: float, b: float) -> float:
    diff = abs(normalize_deg(a - b))
    return min(diff, 360 - diff)


def get_ptolemy_term(sign: str, degree: float) -> str:
    terms = PTOLEMY_TERMS.get(sign, [])
    for end_degree, ruler in terms:
        if degree <= end_degree:
            return ruler
    return terms[-1][1] if terms else ""


def house_from_cusps(lon: float, cusps: List[float]) -> int:
    lon = normalize_deg(lon)
    for i in range(12):
        start = normalize_deg(cusps[i])
        end = normalize_deg(cusps[(i + 1) % 12])
        if start <= end:
            if start <= lon < end:
                return i + 1
        else:
            if lon >= start or lon < end:
                return i + 1
    return 1


def calculate_chart(
    year: int, month: int, day: int,
    hour: int, minute: int,
    timezone: float,
    lat: float, lon_geo: float,
    house_system: str = "P"
) -> Tuple[Dict[str, BodyPosition], List[float], Dict[str, float]]:
    if not SWISSEPH_AVAILABLE:
        raise RuntimeError("مكتبة pyswisseph غير مثبتة. نفّذ: pip install pyswisseph")

    local_decimal = hour + minute / 60.0
    ut_decimal = local_decimal - timezone

    base = datetime(year, month, day)
    day_shift = 0
    while ut_decimal < 0:
        ut_decimal += 24
        day_shift -= 1
    while ut_decimal >= 24:
        ut_decimal -= 24
        day_shift += 1

    from datetime import timedelta
    ut_date = base + timedelta(days=day_shift)

    jd_ut = swe.julday(ut_date.year, ut_date.month, ut_date.day, ut_decimal)
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED

    cusps_tuple, ascmc = swe.houses(jd_ut, lat, lon_geo, house_system.encode("ascii"))
    cusps = list(cusps_tuple[:12])

    positions: Dict[str, BodyPosition] = {}
    for key, meta in PLANETS.items():
        result, retflag = swe.calc_ut(jd_ut, meta["id"], flags)
        p_lon = normalize_deg(result[0])
        speed = result[3]
        sign, degree = sign_from_lon(p_lon)
        house = house_from_cusps(p_lon, cusps)
        term = get_ptolemy_term(sign, degree)
        positions[key] = BodyPosition(
            name_en=key,
            name_ar=meta["ar"],
            lon=p_lon,
            sign=sign,
            degree=degree,
            house=house,
            term=term,
            retrograde=speed < 0
        )

    asc = normalize_deg(ascmc[0])
    mc = normalize_deg(ascmc[1])
    asc_sign, asc_degree = sign_from_lon(asc)
    mc_sign, mc_degree = sign_from_lon(mc)

    angles = {
        "ASC": asc,
        "MC": mc,
        "ASC_sign": asc_sign,
        "ASC_degree": asc_degree,
        "MC_sign": mc_sign,
        "MC_degree": mc_degree,
        "JD_UT": jd_ut
    }

    return positions, cusps, angles


# ============================================================
# محرك التفسير V1
# ============================================================

def add_unique(items: List[str], text: str):
    if text not in items:
        items.append(text)


def analyze_elements(positions: Dict[str, BodyPosition]) -> Dict[str, int]:
    weights = {
        "Sun": 3, "Moon": 3, "Mercury": 2, "Venus": 2,
        "Mars": 2, "Jupiter": 1, "Saturn": 1
    }
    scores = {"نار": 0, "تراب": 0, "هواء": 0, "ماء": 0}
    for key, weight in weights.items():
        sign = positions[key].sign
        scores[ELEMENTS[sign]] += weight
    return scores


def strongest_element(scores: Dict[str, int]) -> str:
    return max(scores, key=lambda k: scores[k])


def detect_major_aspects(positions: Dict[str, BodyPosition]) -> List[Tuple[str, str, str, float]]:
    aspect_defs = [
        ("اقتران", 0, 8),
        ("تسديس", 60, 4),
        ("تربيع", 90, 6),
        ("تثليث", 120, 6),
        ("مقابلة", 180, 6),
    ]
    keys = list(positions.keys())
    aspects = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = positions[keys[i]]
            b = positions[keys[j]]
            dist = angular_distance(a.lon, b.lon)
            for asp_name, asp_deg, orb in aspect_defs:
                if abs(dist - asp_deg) <= orb:
                    aspects.append((a.name_ar, b.name_ar, asp_name, round(abs(dist - asp_deg), 2)))
                    break
    return aspects


def generate_strengths(positions, angles, element_scores, aspects) -> List[str]:
    strengths: List[str] = []

    sun = positions["Sun"]
    moon = positions["Moon"]
    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    jupiter = positions["Jupiter"]
    saturn = positions["Saturn"]
    asc_sign = str(angles["ASC_sign"])
    asc_ruler = SIGN_RULERS[asc_sign]

    dominant = strongest_element(element_scores)
    if dominant == "نار":
        add_unique(strengths, "يمتلك دافعًا داخليًا واضحًا، وحضورًا قويًا عند البدء أو المبادرة، وهذا يساعده على التحرك حين يتردد الآخرون.")
    elif dominant == "تراب":
        add_unique(strengths, "يمتلك حسًا عمليًا وقدرة على بناء النتائج خطوة بعد خطوة، وهذا يمنحه قابلية جيدة للثبات وتحويل الأفكار إلى واقع.")
    elif dominant == "هواء":
        add_unique(strengths, "يمتلك عقلًا نشطًا وقدرة على الفهم والربط والكلام، وهذا يجعله مناسبًا للتعلم والتواصل وتبادل الأفكار.")
    elif dominant == "ماء":
        add_unique(strengths, "يمتلك حسًا عاطفيًا وحدسًا عاليًا، ويستطيع التقاط ما لا يُقال بسهولة، وهذا يساعده في فهم الناس والظروف العميقة.")

    if sun.house in [1, 5, 9, 10, 11]:
        add_unique(strengths, "لديه طاقة ظهور وتأثير، وقد يستطيع أن يترك بصمة واضحة عندما يجد المجال المناسب للتعبير عن ذاته.")
    if moon.house in [4, 5, 7, 9, 11]:
        add_unique(strengths, "يمتلك قابلية للتعاطف وبناء روابط إنسانية، وقد يكون وجوده مطمئنًا لمن حوله إذا شعر بالأمان الداخلي.")
    if mercury.house in [1, 3, 6, 9, 10]:
        add_unique(strengths, "قوة التفكير والملاحظة من أبرز مفاتيحه، ولديه قابلية جيدة للتعلم، التحليل، الكتابة، أو شرح الأفكار.")
    if venus.house in [1, 2, 5, 7, 10, 11]:
        add_unique(strengths, "فيه ذوق وحس جمالي أو اجتماعي، ويستطيع جذب القبول عندما يستخدم اللطف والمرونة بدل الضغط.")
    if mars.house in [1, 3, 6, 10]:
        add_unique(strengths, "يمتلك طاقة عمل ومواجهة، وإذا وجّهها جيدًا يصبح قادرًا على الإنجاز والدفاع عن أهدافه.")
    if jupiter.house in [1, 2, 5, 9, 10, 11]:
        add_unique(strengths, "لديه قابلية للنمو والتوسع واكتساب الخبرة، وقد يستفيد كثيرًا من التعليم والسفر والانفتاح على تجارب جديدة.")
    if saturn.house in [1, 6, 10, 11]:
        add_unique(strengths, "رغم وجود المسؤوليات، لديه قدرة على النضج والتحمل وبناء مكانة تدريجية إذا التزم بخطة طويلة النفس.")

    add_unique(strengths, f"حاكم الطالع هو {asc_ruler}، وهذا يجعله مفتاحًا مهمًا في فهم الشخصية واتجاه الحياة؛ كلما نضجت دلالته في الخريطة ظهر الشخص بصورة أقوى وأكثر توازنًا.")

    for a, b, asp, orb in aspects:
        if asp in ["تثليث", "تسديس"] and ("الشمس" in [a, b] or "القمر" in [a, b] or "عطارد" in [a, b] or "الزهرة" in [a, b]):
            add_unique(strengths, f"يوجد انسجام بين {a} و{b}، وهذا يعطي قابلية طبيعية لاستخدام هذه الطاقة بصورة إيجابية عند التدريب والوعي.")
            break

    return strengths[:6]


def generate_growth_notes(positions, element_scores, aspects) -> List[str]:
    notes: List[str] = []

    weakest = min(element_scores, key=lambda k: element_scores[k])
    if weakest == "نار":
        add_unique(notes, "يحتاج إلى تقوية روح المبادرة وعدم انتظار التشجيع دائمًا قبل البدء.")
    elif weakest == "تراب":
        add_unique(notes, "يحتاج إلى تحويل الأفكار والمشاعر إلى خطوات عملية، لأن كثرة التخطيط بلا تنفيذ قد تضعف النتائج.")
    elif weakest == "هواء":
        add_unique(notes, "يحتاج إلى التعبير والحوار وعدم كتمان الأفكار، لأن الصمت الطويل قد يخلق سوء فهم.")
    elif weakest == "ماء":
        add_unique(notes, "يحتاج إلى الإصغاء لمشاعره وعدم تجاهل الجانب العاطفي، لأن التماسك الظاهري لا يعني غياب التأثر الداخلي.")

    moon = positions["Moon"]
    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    saturn = positions["Saturn"]

    if moon.sign in ["الجدي", "العقرب", "العذراء"]:
        add_unique(notes, "قد يميل إلى ضبط مشاعره أو إخفائها، لذلك يحتاج إلى مساحة آمنة للتعبير بدل الكتمان الطويل.")
    if mercury.retrograde:
        add_unique(notes, "طريقة تفكيره قد تكون داخلية وعميقة، لكنه يحتاج إلى التأكد من وضوح كلامه حتى لا يُفهم بعكس ما يقصد.")
    if venus.sign in ["الحمل", "العذراء", "العقرب", "الجدي"]:
        add_unique(notes, "في العلاقات أو القبول العاطفي يحتاج إلى التوازن بين الرغبة والسيطرة أو بين الحب والخوف من الخيبة.")
    if mars.sign in ["الحمل", "العقرب", "الجدي"]:
        add_unique(notes, "طاقته قوية، لكنها تحتاج إلى تهذيب حتى لا تتحول إلى اندفاع أو توتر في المواقف الحساسة.")
    if saturn.house in [1, 4, 7, 10, 12]:
        add_unique(notes, "قد يشعر بثقل مسؤولية أو جدية مبكرة في أحد محاور حياته، لذلك يحتاج إلى عدم القسوة على نفسه.")

    for a, b, asp, orb in aspects:
        if asp in ["تربيع", "مقابلة"]:
            if "القمر" in [a, b]:
                add_unique(notes, f"يوجد ضغط على الجانب النفسي والعاطفي بين {a} و{b}، وهذا يحتاج إلى وعي بالمشاعر قبل اتخاذ القرارات.")
            elif "المريخ" in [a, b]:
                add_unique(notes, f"يوجد توتر حركي أو انفعالي بين {a} و{b}، ومن الأفضل تصريف الطاقة في عمل أو رياضة أو إنجاز واضح.")
            elif "زحل" in [a, b]:
                add_unique(notes, f"يوجد اختبار في الصبر والمسؤولية بين {a} و{b}، وهذا لا يعني الفشل بل يعني أن النجاح يحتاج إلى وقت وتنظيم.")
    return notes[:6]


def generate_creativity(positions, angles, element_scores) -> List[str]:
    creativity: List[str] = []

    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    sun = positions["Sun"]
    moon = positions["Moon"]
    jupiter = positions["Jupiter"]

    if mercury.house in [1, 3, 6, 9, 10] or mercury.sign in ["الجوزاء", "العذراء", "الدلو"]:
        add_unique(creativity, "الإبداع الذهني واللغوي: الكتابة، التعليم، الشرح، التحليل، البرمجة، أو ترتيب المعلومات.")
    if venus.house in [1, 2, 5, 7, 10] or venus.sign in ["الثور", "الميزان", "الحوت"]:
        add_unique(creativity, "الإبداع الجمالي والاجتماعي: التصميم، الذوق، الفن، التجميل، العلاقات العامة، أو صناعة أجواء مريحة حوله.")
    if mars.house in [1, 3, 5, 6, 10] or mars.sign in ["الحمل", "الأسد", "العقرب", "الجدي"]:
        add_unique(creativity, "الإبداع العملي والحركي: الإنجاز، المبادرة، العمل الميداني، الرياضة، القيادة، أو المشاريع التي تحتاج شجاعة.")
    if moon.house in [4, 5, 8, 12] or moon.sign in ["السرطان", "العقرب", "الحوت"]:
        add_unique(creativity, "الإبداع العاطفي والحدسي: فهم النفوس، الرعاية، العلاج، القصص، التأمل، أو قراءة ما وراء الظاهر.")
    if jupiter.house in [3, 9, 10, 11] or jupiter.sign in ["القوس", "الحوت", "السرطان"]:
        add_unique(creativity, "الإبداع المعرفي والتوجيهي: التعليم العالي، الإرشاد، السفر، الفلسفة، أو تحويل التجارب إلى حكمة.")
    if sun.house in [5, 10, 11] or sun.sign in ["الحمل", "الأسد", "القوس"]:
        add_unique(creativity, "الإبداع القيادي: الظهور، التأثير في الجمهور، إدارة مبادرة، أو تقديم نفسه بثقة أمام الآخرين.")

    dominant = strongest_element(element_scores)
    if dominant == "نار":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة التي تسمح بالمبادرة والقرار السريع وعدم تقييد الحماس.")
    elif dominant == "تراب":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة المنظمة التي تسمح ببناء نتائج ملموسة وقياس التقدم.")
    elif dominant == "هواء":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة التي تسمح بالحوار، الأفكار، التعلم، والتواصل مع الناس.")
    elif dominant == "ماء":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة الهادئة التي تسمح بالتركيز العاطفي والحدسي والتعبير العميق.")

    return creativity[:6] if creativity else ["الإبداع يظهر عندما يُمنح الشخص وقتًا كافيًا لاكتشاف ما يحب، بدل دفعه إلى مجال لا يشبه طبيعته."]


def generate_challenges(positions, aspects) -> List[str]:
    challenges: List[str] = []

    moon = positions["Moon"]
    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    saturn = positions["Saturn"]
    neptune = positions["Neptune"]
    pluto = positions["Pluto"]

    if moon.house in [8, 12] or moon.sign in ["العقرب", "الجدي", "الحوت"]:
        add_unique(challenges, "نخشى عليه من كتمان المشاعر أو حمل أعباء نفسية بصمت، لذلك يحتاج إلى شخص أو مساحة يستطيع أن يتكلم فيها بصدق.")
    if mercury.house in [6, 8, 12] or mercury.sign in ["العذراء", "الجوزاء", "العقرب"]:
        add_unique(challenges, "نخشى عليه من التفكير الزائد أو تحليل التفاصيل بطريقة متعبة، خصوصًا وقت القلق أو انتظار النتائج.")
    if venus.house in [8, 12] or venus.sign in ["العقرب", "العذراء", "الجدي", "الحمل"]:
        add_unique(challenges, "في العلاقات، يحتاج إلى الحذر من التعلق المرهق أو اختبار الحب بطريقة قاسية على نفسه وعلى الآخر.")
    if mars.house in [1, 7, 8, 12] or mars.sign in ["الحمل", "العقرب", "الجدي"]:
        add_unique(challenges, "نخشى عليه من الانفعال السريع أو الدخول في مواجهة قبل اكتمال الصورة، لذلك يحتاج إلى مهلة قصيرة قبل القرار.")
    if saturn.house in [1, 4, 7, 10, 12]:
        add_unique(challenges, "قد تظهر في حياته مسؤوليات أو شعور بالضغط، والتحدي هنا أن لا يتحول الالتزام إلى قسوة على الذات.")
    if neptune.house in [1, 7, 10, 12]:
        add_unique(challenges, "يحتاج إلى وضوح في الوعود والعلاقات والاختيارات، لأن الغموض الطويل قد يجعله يعلّق آماله على صورة غير مكتملة.")
    if pluto.house in [1, 4, 7, 8, 10]:
        add_unique(challenges, "قد يمر بتجارب عميقة تغيّر نظرته لنفسه أو للناس، والتحدي أن لا يسمح للخوف أو السيطرة بأن يقود قراراته.")

    for a, b, asp, orb in aspects:
        if asp in ["تربيع", "مقابلة"]:
            if set([a, b]) & set(["القمر", "الزهرة"]):
                add_unique(challenges, f"هناك حساسية عاطفية واضحة مرتبطة باتصال {a} مع {b}، لذلك من المهم عدم اتخاذ قرار عاطفي في لحظة ضغط.")
            if set([a, b]) & set(["عطارد", "المريخ"]):
                add_unique(challenges, f"اتصال {a} مع {b} قد يزيد حدّة الكلام أو سرعة الرد، لذلك يحتاج إلى تهدئة الفكرة قبل التعبير عنها.")
            if set([a, b]) & set(["زحل"]):
                add_unique(challenges, f"اتصال {a} مع {b} قد يدل على اختبار وتأخير، لكنه يصبح مصدر قوة إذا قُوبل بالصبر والتنظيم.")

    return challenges[:7] if challenges else ["التحدي الأهم ليس وجود خطر واضح، بل ضرورة اختيار البيئة المناسبة وعدم ترك الطاقات القوية بلا توجيه."]




def gender_words(gender: str) -> Dict[str, str]:
    """
    كلمات توجيه الخطاب حسب الجنس المختار.
    نستخدمها في جمل موجهة، لا في استبدال عشوائي داخل الكلمات.
    """
    if gender == "أنثى":
        return {
            "you": "أنتِ",
            "can": "تستطيعين",
            "need": "تحتاجين",
            "have": "لديكِ",
            "appear": "تظهرين",
            "carry": "تحملين",
            "benefit": "تستفيدين",
            "watch": "تنتبهين",
            "your_chart": "خريطتكِ",
            "your_self": "نفسكِ",
            "your_life": "حياتكِ",
            "your_energy": "طاقتكِ",
            "owner": "صاحبة الخريطة",
        }
    return {
        "you": "أنتَ",
        "can": "تستطيع",
        "need": "تحتاج",
        "have": "لديك",
        "appear": "تظهر",
        "carry": "تحمل",
        "benefit": "تستفيد",
        "watch": "تنتبه",
        "your_chart": "خريطتك",
        "your_self": "نفسك",
        "your_life": "حياتك",
        "your_energy": "طاقتك",
        "owner": "صاحب الخريطة",
    }


def personalize_text(text: str, gender: str) -> str:
    """
    تحويل آمن ومحدود في بدايات الجمل فقط.
    لا نستبدل كلمات مثل: الشخصية، وجوده، أثره... حتى لا تظهر أخطاء لغوية.
    """
    w = gender_words(gender)
    female = gender == "أنثى"

    replacements_start = [
        ("يمتلك ", "تمتلكين " if female else "تمتلك "),
        ("لديه ", "لديكِ " if female else "لديك "),
        ("فيه ", "فيكِ " if female else "فيكَ "),
        ("يحتاج إلى ", "تحتاجين إلى " if female else "تحتاج إلى "),
        ("قد يميل ", "قد تميلين " if female else "قد تميل "),
        ("قد يشعر ", "قد تشعرين " if female else "قد تشعر "),
        ("نخشى عليه ", "نخشى عليكِ " if female else "نخشى عليكَ "),
    ]

    for old, new in replacements_start:
        if text.startswith(old):
            text = new + text[len(old):]

    return text


def personalize_list(items: List[str], gender: str) -> List[str]:
    return [personalize_text(x, gender) for x in items]


HOUSE_MEANINGS = {
    1: "الشخصية، المظهر، طريقة البدء، الجسد، والانطباع الأول.",
    2: "المال، الثقة بالنفس، القيم، الممتلكات، وطريقة التعامل مع الموارد.",
    3: "التفكير، الكلام، الدراسة الأولى، الإخوة، التنقلات القصيرة، وطريقة تبادل المعلومات.",
    4: "العائلة، الجذور، البيت، الذاكرة الداخلية، والأمان النفسي.",
    5: "الحب، الأبناء، الإبداع، المتعة، الهوايات، وطريقة إظهار الفرح.",
    6: "الصحة اليومية، العمل الروتيني، الخدمة، الالتزامات، والعادات المتكررة.",
    7: "الزواج، الشراكات، العلاقات المباشرة، الخصوم، وطريقة التعامل مع الآخر.",
    8: "التحولات، الأزمات، المال المشترك، الخوف العميق، والقدرة على التجدد.",
    9: "السفر، التعليم العالي، الدين، الفلسفة، القانون، والرؤية الواسعة للحياة.",
    10: "المهنة، السمعة، المكانة، الطموح، والظهور أمام المجتمع.",
    11: "الأصدقاء، الجماعات، الدعم الاجتماعي، الأمنيات، والمشاريع المستقبلية.",
    12: "العزلة، الأسرار، اللاوعي، التعب الخفي، الروحانية، وما يعمل خلف الكواليس.",
}

PLANET_MEANINGS = {
    "Sun": "الهوية والإرادة والوعي والقدرة على الظهور.",
    "Moon": "النفس والمشاعر والذاكرة والاحتياج إلى الأمان.",
    "Mercury": "التفكير والكلام والتعلم وطريقة فهم المعلومات.",
    "Venus": "الحب والقبول والجمال والذوق والمال اللطيف.",
    "Mars": "الفعل والشجاعة والغضب والرغبة وطريقة المواجهة.",
    "Jupiter": "التوسع والفرص والمعرفة والثقة والنمو.",
    "Saturn": "المسؤولية والحدود والصبر والتأخير والنضج.",
    "Uranus": "التحرر والمفاجآت والاستقلال والتغيير غير المتوقع.",
    "Neptune": "الخيال والروحانية والإلهام والغموض والضبابية.",
    "Pluto": "التحول العميق والسيطرة والقوة الداخلية وإعادة البناء.",
}

# ============================================================
# دستورية الكواكب في الأبراج والبيوت
# مستخرجة من منهج: Home / Fall / Detriment / Exaltation
# مع قوة وضعف البيت كما في الصور المرفقة.
# ============================================================

PLANET_CONSTITUTION = {
    "Sun": {
        "home": ["الأسد"],
        "exaltation": ["الحمل"],
        "detriment": ["الدلو"],
        "fall": ["الميزان"],
        "strong_houses": [9, 10, 11],
        "weak_houses": [3, 4, 5],
        "notes": "الشمس تقوى عندما تجد مجالًا للظهور والقيادة والمعنى، وتضعف عندما تُحاصر الهوية أو تصبح القيمة الذاتية مرتبطة برضا الآخرين."
    },
    "Moon": {
        "home": ["السرطان"],
        "exaltation": ["الثور"],
        "detriment": ["الجدي"],
        "fall": ["العقرب"],
        "strong_houses": [2, 4],
        "weak_houses": [6, 8, 10, 12],
        "notes": "القمر يقوى حيث يوجد أمان واحتواء واستقرار نفسي، ويضعف عندما تُضغط المشاعر أو تُجبر على الكتمان أو العمل تحت توتر دائم."
    },
    "Mercury": {
        "home": ["الجوزاء", "العذراء"],
        "exaltation": ["الدلو"],
        "detriment": ["القوس", "الحوت"],
        "fall": ["الأسد"],
        "strong_houses": [1, 2],
        "weak_houses": [7, 8, 12],
        "notes": "عطارد يقوى عندما يجد وضوحًا في التفكير والكلام والتجارة والتعلّم، ويضعف عندما يدخل في غموض أو تشويش أو ردود فعل عاطفية مفرطة."
    },
    "Venus": {
        "home": ["الثور", "الميزان"],
        "exaltation": ["الحوت"],
        "detriment": ["العقرب", "الحمل"],
        "fall": ["العذراء"],
        "strong_houses": [2, 4, 7],
        "weak_houses": [6, 8, 10],
        "notes": "الزهرة تقوى في بيوت القبول والراحة والعلاقة والقيمة، وتضعف عندما تُدفع إلى الضغط أو الواجب أو الصراع أو النقد الزائد."
    },
    "Mars": {
        "home": ["الحمل", "العقرب"],
        "exaltation": ["الجدي"],
        "detriment": ["الميزان", "الثور"],
        "fall": ["السرطان"],
        "strong_houses": [1, 10],
        "weak_houses": [4, 6, 12],
        "notes": "المريخ يقوى عندما يجد هدفًا ومواجهة وإنجازًا، ويضعف عندما تُحبس طاقته في الخفاء أو العائلة أو التعب اليومي بلا تصريف."
    },
    "Jupiter": {
        "home": ["القوس", "الحوت"],
        "exaltation": ["السرطان"],
        "detriment": ["الجوزاء", "العذراء"],
        "fall": ["الجدي"],
        "strong_houses": [1, 4, 9],
        "weak_houses": [6, 7, 8],
        "notes": "المشتري يقوى في المعنى والتعليم والسفر والحماية، ويضعف عندما تُحصر حكمته في تفاصيل ضيقة أو مسؤوليات ثقيلة أو أزمات مشتركة."
    },
    "Saturn": {
        "home": ["الجدي", "الدلو"],
        "exaltation": ["الميزان"],
        "detriment": ["السرطان"],
        "fall": ["الحمل"],
        "strong_houses": [7, 10, 11],
        "weak_houses": [1, 4],
        "notes": "زحل يقوى في المسؤولية والبناء والمكانة والقوانين، ويضعف عندما يضغط على الذات أو الجذور النفسية فيصنع ثقلًا داخليًا."
    },
    "Uranus": {
        "home": ["الدلو"],
        "exaltation": ["العقرب"],
        "detriment": ["الأسد"],
        "fall": ["الثور"],
        "strong_houses": [8, 11],
        "weak_houses": [2, 5],
        "notes": "أورانوس يقوى في التجديد والتحرر والتحولات والجماعات، ويضعف عندما يصطدم بالتملك أو الثبات أو الحاجة إلى أمان مادي جامد."
    },
    "Neptune": {
        "home": ["الحوت"],
        "exaltation": ["السرطان"],
        "detriment": ["العذراء"],
        "fall": ["الجدي"],
        "strong_houses": [4, 12],
        "weak_houses": [6, 10],
        "notes": "نبتون يقوى في الروحانية والخيال والعمق الداخلي، ويضعف عندما يدخل في العمل الصارم أو السمعة أو التفاصيل التي تحتاج وضوحًا حادًا."
    },
    "Pluto": {
        "home": ["العقرب"],
        "exaltation": ["الأسد"],
        "detriment": ["الثور"],
        "fall": ["الدلو"],
        "strong_houses": [5, 8],
        "weak_houses": [2, 11],
        "notes": "بلوتو يقوى في التحول العميق والسيطرة الواعية وإعادة البناء، ويضعف عندما يتجمد في التملك أو صراعات الجماعة أو الخوف من خسارة القيمة."
    },
}



PLANET_PERSONALITY_REFLECTIONS = {
    "Sun": {
        "strong": "انعكاس القوة على الشخصية: إرادة أوضح، ثقة أعلى، قدرة على القيادة، وحاجة طبيعية إلى ترك أثر. إذا نضجت هذه القوة تعطي حضورًا وكرامة واستقلالًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تردد في إثبات الذات، أو ربط القيمة الشخصية برأي الآخرين، أو خوف من الظهور. يحتاج الفرد إلى بناء ثقته خطوة بعد خطوة وعدم انتظار الاعتراف الخارجي دائمًا."
    },
    "Moon": {
        "strong": "انعكاس القوة على الشخصية: حس عاطفي واضح، قدرة على الاحتواء، ذاكرة قوية، واستجابة وجدانية تساعد على فهم الناس. إذا نضجت هذه القوة تعطي أمانًا داخليًا وتعاطفًا عميقًا.",
        "weak": "انعكاس الضعف على الشخصية: قد تظهر حساسية زائدة، تقلب مزاج، كتمان للمشاعر، أو صعوبة في طلب الأمان. يحتاج الفرد إلى التعبير عن مشاعره وعدم حمل العبء النفسي بصمت."
    },
    "Mercury": {
        "strong": "انعكاس القوة على الشخصية: عقل سريع أو منظم، قدرة على التعلم، التحليل، الكلام، الكتابة، وربط المعلومات. إذا نضجت هذه القوة تجعل الفرد مقنعًا وذكيًا في التعامل مع التفاصيل.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تشتت، قلق ذهني، سوء فهم، أو صعوبة في ترتيب الأفكار. يحتاج الفرد إلى تنظيم التفكير والتأكد من وضوح الكلام قبل إصدار الحكم."
    },
    "Venus": {
        "strong": "انعكاس القوة على الشخصية: ذوق، قبول اجتماعي، قدرة على بناء علاقات لطيفة، حس جمالي، وجذب للراحة أو المال أو المحبة. إذا نضجت هذه القوة تعطي توازنًا في الحب والقيمة.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر خوف من الرفض، تعلق عاطفي، صعوبة في تقدير الذات، أو اضطراب في المال والاختيارات الجمالية. يحتاج الفرد إلى عدم قياس قيمته من خلال قبول الآخرين فقط."
    },
    "Mars": {
        "strong": "انعكاس القوة على الشخصية: شجاعة، مبادرة، جرأة، سرعة في الفعل، وقدرة على الدفاع عن الهدف. إذا نضجت هذه القوة تصنع إنجازًا وقيادة عملية.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر غضب مكبوت، اندفاع غير محسوب، خوف من المواجهة، أو صراع داخلي بين الرغبة والفعل. يحتاج الفرد إلى تصريف الطاقة في عمل واضح أو رياضة أو هدف منظم."
    },
    "Jupiter": {
        "strong": "انعكاس القوة على الشخصية: تفاؤل، ثقة، رغبة في التعلم، قابلية للنمو، وانفتاح على السفر أو التجارب الواسعة. إذا نضجت هذه القوة تعطي حكمة وفرصًا ومعنى.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تضخيم للوعود، ثقة زائدة أو العكس، تشتت في الاتجاهات، أو صعوبة في رؤية الفرصة بوضوح. يحتاج الفرد إلى موازنة التفاؤل بالخطة الواقعية."
    },
    "Saturn": {
        "strong": "انعكاس القوة على الشخصية: صبر، التزام، قدرة على تحمل المسؤولية، بناء طويل الأمد، واحترام للقوانين والحدود. إذا نضجت هذه القوة تصنع مكانة وثباتًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر خوف من الفشل، شعور بالثقل، تأخير، قسوة على الذات، أو تجمد أمام المسؤولية. يحتاج الفرد إلى التعامل مع الوقت كحليف لا كعقوبة."
    },
    "Uranus": {
        "strong": "انعكاس القوة على الشخصية: استقلال، أفكار مختلفة، رغبة في التحرر، قدرة على الابتكار، وعدم الخضوع للنمط التقليدي. إذا نضجت هذه القوة تعطي تجديدًا ووعيًا مستقبليًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تمرد مفاجئ، قطيعة، توتر عصبي، أو صعوبة في الاستقرار. يحتاج الفرد إلى التفريق بين الحرية والهروب من الالتزام."
    },
    "Neptune": {
        "strong": "انعكاس القوة على الشخصية: خيال، حدس، رحمة، حس روحي أو فني، وقدرة على الإلهام. إذا نضجت هذه القوة تعطي بصيرة وعمقًا إنسانيًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر ضياع، مثالية زائدة، تعلق بصورة غير واقعية، أو صعوبة في رؤية الحدود. يحتاج الفرد إلى وضوح وحقائق عملية حتى لا يذوب في الوهم."
    },
    "Pluto": {
        "strong": "انعكاس القوة على الشخصية: عمق، قوة داخلية، قدرة على التحول، كشف الخفي، وإعادة البناء بعد الأزمات. إذا نضجت هذه القوة تعطي شخصية مؤثرة وشجاعة في مواجهة الحقيقة.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر خوف من الفقد، رغبة في السيطرة، شك، أو صراعات قوة داخلية وخارجية. يحتاج الفرد إلى تحويل السيطرة إلى وعي، والخوف إلى قدرة على التجدد."
    },
}


def planet_personality_reflection(key: str, score: int) -> str:
    data = PLANET_PERSONALITY_REFLECTIONS.get(key, {})
    if score >= 20:
        return data.get("strong", "")
    if score <= -20:
        return data.get("weak", "")
    strong = data.get("strong", "")
    weak = data.get("weak", "")
    return (
        "انعكاسه على الشخصية: تأثير هذا الكوكب متوسط، لذلك قد تظهر صفاته الإيجابية عند الوعي والتدريب، "
        "وتظهر تحدياته عند الضغط أو سوء التوجيه. "
        + strong.replace("انعكاس القوة على الشخصية:", "في جانبه الإيجابي:").replace("إذا نضجت هذه القوة", "إذا نضج هذا التأثير")
        + " "
        + weak.replace("انعكاس الضعف على الشخصية:", "وفي جانبه الذي يحتاج وعيًا:").replace("يحتاج الفرد", "لذلك يحتاج الفرد")
    )


def planet_sign_dignity(key: str, sign: str) -> Dict[str, object]:
    data = PLANET_CONSTITUTION.get(key, {})
    score = 0
    status = "حيادي"
    text = "لا يظهر للكوكب حكم دستوري خاص في هذا البرج، لذلك تُقرأ قوته من البيت والحد والاتصالات."

    if sign in data.get("home", []):
        score = 30
        status = "موطن"
        text = "الكوكب في موطنه، وهذا يعطيه قدرة طبيعية على التعبير عن دلالته بصورة أوضح وأكثر أصالة."
    elif sign in data.get("exaltation", []):
        score = 25
        status = "شرف / تمجيد"
        text = "الكوكب في موضع شرف أو تمجيد، فيعمل بقوة عالية لكن يحتاج إلى توجيه حتى لا يبالغ في دلالته."
    elif sign in data.get("detriment", []):
        score = -25
        status = "وبال / تضرر"
        text = "الكوكب في موضع وبال أو تضرر، فلا يفقد معناه لكنه يحتاج إلى وعي أكبر حتى لا يظهر بصورة معاكسة لطبيعته."
    elif sign in data.get("fall", []):
        score = -30
        status = "هبوط"
        text = "الكوكب في موضع هبوط، وهذا لا يعني العجز، بل يعني أن دلالته تحتاج إلى تدريب وتهذيب قبل أن تعمل بسهولة."

    return {"status": status, "score": score, "text": text}


def planet_house_strength(key: str, house: int) -> Dict[str, object]:
    data = PLANET_CONSTITUTION.get(key, {})
    score = 0
    status = "متوسط"
    text = "هذا البيت لا يقوّي الكوكب ولا يضعفه بصورة حاسمة، لذلك نرجع إلى البرج والحد والاتصالات."

    if house in data.get("strong_houses", []):
        score = 20
        status = "قوي في البيت"
        text = "موقع الكوكب في هذا البيت يدعم طبيعته ويجعل أثره أوضح في حياة الشخص."
    elif house in data.get("weak_houses", []):
        score = -20
        status = "ضعيف في البيت"
        text = "موقع الكوكب في هذا البيت لا ينسجم بسهولة مع طبيعته، لذلك يحتاج إلى وعي وتنظيم حتى لا يتحول إلى ضغط."

    return {"status": status, "score": score, "text": text}


def planet_constitution_analysis(key: str, p: BodyPosition) -> Dict[str, object]:
    sign_eval = planet_sign_dignity(key, p.sign)
    house_eval = planet_house_strength(key, int(p.house or 0))
    total = int(sign_eval["score"]) + int(house_eval["score"])

    if total >= 40:
        level = "قوي جدًا"
    elif total >= 20:
        level = "قوي"
    elif total > -20:
        level = "متوسط"
    elif total > -40:
        level = "ضعيف ويحتاج إلى وعي"
    else:
        level = "ضعيف جدًا ويحتاج إلى معالجة واعية"

    base_note = PLANET_CONSTITUTION.get(key, {}).get("notes", "")

    reflection = planet_personality_reflection(key, total)

    text = (
        f"دستوريًا: {p.name_ar} في {p.sign} = {sign_eval['status']}، "
        f"وفي البيت {p.house} = {house_eval['status']}. "
        f"التقييم العام: {level} بدرجة {total}. "
        f"{sign_eval['text']} {house_eval['text']} {base_note} "
        f"{reflection}"
    )

    return {"level": level, "score": total, "text": text, "reflection": reflection}



SIGN_SIMPLE_TRAITS = {
    "الحمل": "طاقة مباشرة، مبادرة، سريعة الاستجابة، وتحتاج إلى هدف واضح حتى لا تتحول إلى اندفاع.",
    "الثور": "طاقة ثابتة وعملية، تبحث عن الأمان والنتائج الملموسة، وتحتاج إلى المرونة أمام التغيير.",
    "الجوزاء": "طاقة ذهنية متحركة، تحب المعرفة والكلام والتنوع، وتحتاج إلى التركيز حتى لا تتشتت.",
    "السرطان": "طاقة عاطفية حامية، مرتبطة بالأمان والعائلة والذاكرة، وتحتاج إلى عدم المبالغة في الحساسية.",
    "الأسد": "طاقة حضور وكرامة وإبداع، تحب التأثير والاعتراف، وتحتاج إلى توازن بين الفخر والتواضع.",
    "العذراء": "طاقة تحليل وخدمة وتنظيم، ترى التفاصيل بسرعة، وتحتاج إلى عدم إنهاك نفسها بالنقد والمثالية.",
    "الميزان": "طاقة توازن وعلاقات وذوق، تبحث عن العدل والانسجام، وتحتاج إلى حسم القرار بدل إرضاء الجميع.",
    "العقرب": "طاقة عميقة وقوية وحدسية، تدخل إلى جوهر الأمور، وتحتاج إلى تخفيف الشك أو السيطرة.",
    "القوس": "طاقة توسع ومعرفة وسفر، تبحث عن المعنى والحرية، وتحتاج إلى ربط الحماس بخطة واقعية.",
    "الجدي": "طاقة مسؤولية وبناء وطموح، تنجح بالتدرج، وتحتاج إلى عدم القسوة على الذات.",
    "الدلو": "طاقة استقلال وفكر مختلف، تهتم بالجماعة والمستقبل، وتحتاج إلى عدم الانفصال عن العاطفة.",
    "الحوت": "طاقة حدس وخيال ورحمة، تلتقط ما وراء الظاهر، وتحتاج إلى حدود واضحة حتى لا تذوب في الآخرين.",
}

TERM_INTERPRETATION = {
    "الشمس": "الحد الشمسي يضيف رغبة في الظهور والوضوح والثقة، ويجعل الدلالة تميل إلى إثبات الذات.",
    "القمر": "الحد القمري يضيف حساسية واستجابة شعورية، ويجعل الدلالة مرتبطة بالأمان والانفعال الداخلي.",
    "عطارد": "حد عطارد يضيف تفكيرًا وتحليلًا وكلامًا وحركة ذهنية، ويجعل الدلالة عقلية أو تواصلية.",
    "الزهرة": "حد الزهرة يضيف لينًا وقبولًا وذوقًا، ويجعل الدلالة أقرب إلى العلاقات أو الجمال أو التهدئة.",
    "المريخ": "حد المريخ يضيف حرارة واندفاعًا ومواجهة، ويحتاج إلى وعي حتى لا يتحول إلى توتر.",
    "المشتري": "حد المشتري يضيف توسعًا وثقة وفرصة، ويجعل الدلالة قابلة للنمو إذا استُخدمت بحكمة.",
    "زحل": "حد زحل يضيف جدية وتأخيرًا ومسؤولية، ويطلب الصبر والتنظيم قبل ظهور النتائج.",
}


def aspect_sentence_for_planet(planet_ar: str, aspects) -> str:
    related = []
    for a, b, asp, orb in aspects:
        if a == planet_ar:
            related.append(f"{asp} {b}")
        elif b == planet_ar:
            related.append(f"{asp} {a}")
    if not related:
        return "لا تظهر له اتصالات رئيسية قوية ضمن الأورب المعتمد في هذه النسخة، لذلك تُقرأ دلالته أساسًا من البرج والبيت والحد."
    return "أبرز اتصالاته: " + "، ".join(related[:4]) + "."


def planet_reading_text(key: str, p: BodyPosition, aspects) -> str:
    planet_meaning = PLANET_MEANINGS.get(key, "")
    sign_trait = SIGN_SIMPLE_TRAITS.get(p.sign, "")
    term_text = TERM_INTERPRETATION.get(p.term or "", "")
    retro = " وهو متراجع، لذلك تعمل دلالته بطريقة داخلية أو مراجِعة وتحتاج إلى وقت قبل التعبير الواضح." if p.retrograde else ""
    asp_text = aspect_sentence_for_planet(p.name_ar, aspects)
    constitution = planet_constitution_analysis(key, p)

    return (
        f"{p.name_ar}: يمثل {planet_meaning} وجوده في {p.sign} يعطي {sign_trait} "
        f"وموقعه في البيت {p.house} يربط هذه الطاقة بموضوع: {HOUSE_MEANINGS.get(p.house, '')} "
        f"ويقع عند {format_degree(p.degree)} من {p.sign} ضمن حد {p.term}. "
        f"هنا لا نقرأ {p.name_ar} من البرج والبيت فقط، بل ندمج الحد أيضًا؛ {term_text} "
        f"{constitution['text']} "
        f"{retro} {asp_text}"
    )


def house_reading_text(house_num: int, cusp_lon: float, positions) -> str:
    sign, degree = sign_from_lon(cusp_lon)
    ruler = SIGN_RULERS.get(sign, "")
    planets_inside = [p.name_ar for p in positions.values() if p.house == house_num]
    planets_text = " وفيه: " + "، ".join(planets_inside) + "." if planets_inside else " ولا توجد فيه كواكب أساسية، لذلك يُقرأ من البرج الحاكم وحاكم البيت."
    term = get_ptolemy_term(sign, degree)
    term_text = TERM_INTERPRETATION.get(term, "")
    return (
        f"البيت {house_num}: يبدأ في {sign} عند {format_degree(degree)}، ومعناه العام: {HOUSE_MEANINGS[house_num]} "
        f"حاكم هذا البيت هو {ruler}. بداية البيت تقع في حد {term}، وهذا يضيف طبقة تفسيرية إلى معنى البيت؛ {term_text}{planets_text}"
    )


def generate_general_analysis(name: str, positions, angles, element_scores) -> str:
    asc_sign = str(angles["ASC_sign"])
    sun = positions["Sun"]
    moon = positions["Moon"]
    dominant = strongest_element(element_scores)
    asc_ruler = SIGN_RULERS.get(asc_sign, "")

    dominant_text = {
        "نار": "يغلب على الخريطة عنصر النار، وهذا يعطي رغبة في الحركة والمبادرة والتعبير المباشر عن الذات.",
        "تراب": "يغلب على الخريطة عنصر التراب، وهذا يدل على عقلية عملية تبحث عن الثبات والإنجاز والنتائج المحسوسة.",
        "هواء": "يغلب على الخريطة عنصر الهواء، وهذا يشير إلى عقل نشط وتواصل قوي واهتمام بالأفكار والعلاقات الذهنية.",
        "ماء": "يغلب على الخريطة عنصر الماء، وهذا يكشف حساسية وحدسًا وعمقًا نفسيًا وقدرة على التقاط ما وراء الكلام."
    }.get(dominant, "")

    return (
        f"الخريطة العامة لـ {name} تقوم على تفاعل مهم بين الطالع في {asc_sign}، والشمس في {sun.sign}، والقمر في {moon.sign}. "
        f"الطالع يوضح طريقة الدخول إلى الحياة والتعامل الأول مع الناس، والشمس تكشف الإرادة والهوية، والقمر يصف النفس الداخلية والحاجة العاطفية. "
        f"{dominant_text} حاكم الطالع هو {asc_ruler}، لذلك يجب متابعته لأنه يمثل مفتاح الحركة الشخصية واتجاه النمو في الحياة. "
        "هذه القراءة لا تتعامل مع الإنسان كصفة واحدة، بل كتركيب متداخل بين الإرادة والمشاعر والعقل والعمل والعلاقات."
    )


def generate_asc_sun_moon_analysis(positions, angles) -> Dict[str, str]:
    asc_sign = str(angles["ASC_sign"])
    asc_degree = float(angles["ASC_degree"])
    asc_term = get_ptolemy_term(asc_sign, asc_degree)
    asc_ruler = SIGN_RULERS.get(asc_sign, "")

    sun = positions["Sun"]
    moon = positions["Moon"]

    asc_text = (
        f"الطالع في {asc_sign} عند {format_degree(asc_degree)} ضمن حد {asc_term}. "
        f"هذا يصف طريقة ظهور الشخص وبدايته مع الحياة. {SIGN_SIMPLE_TRAITS.get(asc_sign, '')} "
        f"حاكم الطالع هو {asc_ruler}، ولذلك يصبح هذا الحاكم مفتاحًا مهمًا في فهم اتجاه الشخصية ونمط استجابتها."
    )

    sun_text = (
        f"الشمس في {sun.sign} في البيت {sun.house} عند {format_degree(sun.degree)} ضمن حد {sun.term}. "
        f"الشمس تمثل الهوية والإرادة والوعي. {SIGN_SIMPLE_TRAITS.get(sun.sign, '')} "
        f"وجودها في البيت {sun.house} يجعل موضوع {HOUSE_MEANINGS.get(sun.house, '')} مجالًا مهمًا لإثبات الذات وبناء الثقة."
    )

    moon_text = (
        f"القمر في {moon.sign} في البيت {moon.house} عند {format_degree(moon.degree)} ضمن حد {moon.term}. "
        f"القمر يمثل النفس والمشاعر والاحتياج إلى الأمان. {SIGN_SIMPLE_TRAITS.get(moon.sign, '')} "
        f"وجوده في البيت {moon.house} يجعل موضوع {HOUSE_MEANINGS.get(moon.house, '')} مؤثرًا في المزاج الداخلي والراحة النفسية."
    )

    return {"asc": asc_text, "sun": sun_text, "moon": moon_text}


def generate_planetary_analysis(positions, aspects) -> List[str]:
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    return [planet_reading_text(k, positions[k], aspects) for k in order]


def generate_houses_analysis(cusps, positions) -> List[str]:
    return [house_reading_text(i + 1, cusps[i], positions) for i in range(12)]




def modality_scores(positions: Dict[str, BodyPosition]) -> Dict[str, int]:
    modes = {
        "الحمل": "مبادر", "السرطان": "مبادر", "الميزان": "مبادر", "الجدي": "مبادر",
        "الثور": "ثابت", "الأسد": "ثابت", "العقرب": "ثابت", "الدلو": "ثابت",
        "الجوزاء": "متغير", "العذراء": "متغير", "القوس": "متغير", "الحوت": "متغير",
    }
    weights = {
        "Sun": 3, "Moon": 3, "Mercury": 2, "Venus": 2,
        "Mars": 2, "Jupiter": 1, "Saturn": 1
    }
    scores = {"مبادر": 0, "ثابت": 0, "متغير": 0}
    for key, weight in weights.items():
        scores[modes[positions[key].sign]] += weight
    return scores



MIDPOINT_GROUPS = {
    "عاطفيًا": [
        ("الشمس/الزهرة", "Sun", "Venus", "نقطة جاذبية وذوق ومحبة، وتوضح طريقة إظهار القبول والجمال والعاطفة الهادئة."),
        ("القمر/الزهرة", "Moon", "Venus", "نقطة عاطفية رقيقة تكشف الاحتياج إلى الحنان والقبول والراحة النفسية في العلاقات."),
        ("الزهرة/المريخ", "Venus", "Mars", "نقطة الرغبة والجاذبية والحركة العاطفية، وتوضح كيف تمتزج العاطفة بالفعل والرغبة."),
        ("القمر/المريخ", "Moon", "Mars", "نقطة الانفعال العاطفي ورد الفعل، وقد تكشف سرعة التأثر أو الحماس أو الغضب العاطفي."),
        ("الطالع/الزهرة", "ASC", "Venus", "نقطة القبول الشخصي والجاذبية الظاهرة، وتفيد في فهم الطريقة التي يُستقبل بها الشخص عاطفيًا واجتماعيًا."),
    ],
    "مهنيًا": [
        ("الشمس/المريخ", "Sun", "Mars", "نقطة الإرادة والفعل، وتكشف قوة المبادرة والقدرة على الدفاع عن الهدف."),
        ("الشمس/زحل", "Sun", "Saturn", "نقطة المسؤولية والالتزام وبناء المكانة، وتوضح أين يحتاج النجاح إلى صبر وهيكلة."),
        ("الشمس/المشتري", "Sun", "Jupiter", "نقطة التوسع والطموح والثقة، وقد تشير إلى قابلية النمو المهني عند حسن استثمار الفرصة."),
        ("زحل/المريخ", "Saturn", "Mars", "نقطة الضغط بين الفعل والحدود، وتحتاج إلى ضبط الغضب والصبر في الإنجاز والعمل."),
        ("العاشر/الشمس", "MC", "Sun", "نقطة الظهور والسمعة والهوية المهنية، وتكشف علاقة الإرادة الشخصية بالمكانة العامة."),
    ],
    "ماليًا": [
        ("الزهرة/المشتري", "Venus", "Jupiter", "نقطة الوفرة والقبول المالي والفرص السهلة، وتدل على مواضع الاستفادة إذا وُجد وعي بالفرصة."),
        ("الزهرة/زحل", "Venus", "Saturn", "نقطة المال المنظم والحذر المالي، وقد تدل على كسب يأتي بعد تأخير أو مسؤولية."),
        ("المشتري/زحل", "Jupiter", "Saturn", "نقطة التوازن بين التوسع والحدود، وهي مهمة في إدارة المال والاستثمار طويل المدى."),
        ("المريخ/المشتري", "Mars", "Jupiter", "نقطة الجرأة المالية والمخاطرة المحسوبة، وتحتاج إلى خطة حتى لا تتحول إلى اندفاع."),
        ("الثاني/الزهرة", "CUSP2", "Venus", "نقطة الموارد والقيمة الشخصية والقدرة على جذب المال أو تحسين الدخل."),
    ],
    "الدراسة والتفكير": [
        ("عطارد/الزهرة", "Mercury", "Venus", "نقطة الكلام الجميل والذوق في التعبير، وتفيد في الكتابة، الإقناع، الفن، والتعليم اللطيف."),
        ("عطارد/المشتري", "Mercury", "Jupiter", "نقطة المعرفة والسفر والتوسع الذهني، وتفيد في التعليم، التجارة، اللغات، والرؤية الواسعة."),
        ("عطارد/زحل", "Mercury", "Saturn", "نقطة التفكير الجاد والمنهجي، وتفيد في الدراسة العميقة والبحث والتنظيم."),
        ("عطارد/أورانوس", "Mercury", "Uranus", "نقطة الذكاء المفاجئ والأفكار المختلفة، وتفيد في التقنية والابتكار والتحليل السريع."),
        ("الثالث/عطارد", "CUSP3", "Mercury", "نقطة الدراسة الأولى والتواصل والكتابة والتنقلات القصيرة."),
    ],
    "السفر والتوسع": [
        ("المشتري/عطارد", "Jupiter", "Mercury", "نقطة السفر والمعرفة واللغات والتبادل الفكري، وهي من أهم نقاط الحركة الذهنية والجغرافية."),
        ("المشتري/الشمس", "Jupiter", "Sun", "نقطة الرؤية الواسعة والثقة والانفتاح على تجارب أكبر من البيئة المعتادة."),
        ("المشتري/القمر", "Jupiter", "Moon", "نقطة الراحة في التوسع وتغيير المكان، وقد تعطي قابلية نفسية للاستفادة من السفر أو الانتقال."),
        ("التاسع/المشتري", "CUSP9", "Jupiter", "نقطة السفر البعيد والتعليم العالي والرؤية الفلسفية أو الدينية."),
        ("التاسع/عطارد", "CUSP9", "Mercury", "نقطة الدراسة العليا واللغات والتواصل مع بيئات مختلفة."),
    ],
}


def get_point_lon(key: str, positions: Dict[str, BodyPosition], cusps: List[float], angles: Dict[str, float]) -> float:
    """
    تحويل اسم النقطة إلى طول فلكي.
    يدعم الكواكب، الطالع، العاشر، وبعض رؤوس البيوت.
    """
    if key in positions:
        return float(positions[key].lon)
    if key == "ASC":
        return float(angles["ASC"])
    if key == "MC":
        return float(angles["MC"])
    if key.startswith("CUSP"):
        house_num = int(key.replace("CUSP", ""))
        return float(cusps[house_num - 1])
    raise ValueError(f"نقطة غير معروفة: {key}")


def midpoint_short_arc(lon1: float, lon2: float) -> float:
    """
    حساب نقطة المنتصف على القوس الأقصر.
    """
    a = normalize_deg(lon1)
    b = normalize_deg(lon2)
    diff = normalize_deg(b - a)
    if diff > 180:
        diff -= 360
    return normalize_deg(a + diff / 2.0)


def midpoint_activation_text(mid_lon: float, positions: Dict[str, BodyPosition], orb: float = 2.0) -> str:
    """
    فحص تفعيل نقطة المنتصف من كواكب الميلاد بالاقتران/التربيع/المقابلة.
    """
    hits = []
    for p in positions.values():
        d0 = angular_distance(mid_lon, p.lon)
        d90 = abs(angular_distance(mid_lon, p.lon) - 90)
        d180 = abs(angular_distance(mid_lon, p.lon) - 180)

        if d0 <= orb:
            hits.append(f"{p.name_ar} يقترن بها")
        elif d90 <= orb:
            hits.append(f"{p.name_ar} يربعها")
        elif d180 <= orb:
            hits.append(f"{p.name_ar} يقابلها")

    if hits:
        return " وهي مفعّلة في الخريطة عبر: " + "، ".join(hits[:4]) + "."
    return " ولا يظهر عليها تفعيل قوي من كواكب الميلاد ضمن أورب درجتين، لكنها تبقى نقطة حساسة عند العبور أو التقدم."


def midpoint_priority_score(mid_lon: float, house: int, term: str, positions: Dict[str, BodyPosition]) -> int:
    """
    درجة بسيطة لترتيب نقاط المنتصف داخل كل موضوع.
    """
    score = 0

    if house in [1, 4, 7, 10]:
        score += 25
    elif house in [2, 5, 8, 9, 11]:
        score += 15
    else:
        score += 8

    if term in ["الشمس", "القمر", "الزهرة", "المشتري"]:
        score += 12
    elif term in ["عطارد", "المريخ"]:
        score += 8
    elif term == "زحل":
        score += 6

    for p in positions.values():
        d0 = angular_distance(mid_lon, p.lon)
        d90 = abs(angular_distance(mid_lon, p.lon) - 90)
        d180 = abs(angular_distance(mid_lon, p.lon) - 180)
        if d0 <= 2 or d90 <= 2 or d180 <= 2:
            score += 25
            break

    return score


def midpoint_item_text(label: str, a_key: str, b_key: str, meaning: str, positions, cusps, angles) -> Dict[str, object]:
    lon1 = get_point_lon(a_key, positions, cusps, angles)
    lon2 = get_point_lon(b_key, positions, cusps, angles)
    mid_lon = midpoint_short_arc(lon1, lon2)
    sign, degree = sign_from_lon(mid_lon)
    house = house_from_cusps(mid_lon, cusps)
    term = get_ptolemy_term(sign, degree)
    activation = midpoint_activation_text(mid_lon, positions)
    score = midpoint_priority_score(mid_lon, house, term, positions)

    text = (
        f"نقطة {label} تقع في {sign} عند {format_degree(degree)} في البيت {house} وضمن حد {term}. "
        f"{meaning} "
        f"وجودها في البيت {house} يربطها بموضوع: {HOUSE_MEANINGS.get(house, '')} "
        f"أما حد {term} فيعطيها النوعية التالية: {TERM_INTERPRETATION.get(term, '')} "
        f"{activation}"
    )

    return {"text": text, "score": score}


def generate_midpoints_analysis(positions, cusps, angles) -> List[Dict[str, object]]:
    """
    تحليل نقاط المنتصف حسب الموضوعات:
    عاطفية، مهنية، مالية، دراسة وتفكير، سفر وتوسع.
    """
    groups: List[Dict[str, object]] = []

    for group_title, definitions in MIDPOINT_GROUPS.items():
        items = []
        for label, a_key, b_key, meaning in definitions:
            try:
                items.append(midpoint_item_text(label, a_key, b_key, meaning, positions, cusps, angles))
            except Exception:
                continue

        # ترتيب النقاط داخل كل محور حسب الأهمية لا حسب الإدخال فقط
        items.sort(key=lambda x: int(x["score"]), reverse=True)

        groups.append({
            "title": group_title,
            "items": [x["text"] for x in items]
        })

    return groups


def generate_terms_analysis(positions, angles) -> List[str]:
    """
    تحليل حدود بطليموس كقسم مستقل.
    """
    items: List[str] = []

    asc_sign = str(angles["ASC_sign"])
    asc_degree = float(angles["ASC_degree"])
    asc_term = get_ptolemy_term(asc_sign, asc_degree)
    items.append(
        f"الطالع يقع في حد {asc_term}. {TERM_INTERPRETATION.get(asc_term, '')} "
        "لذلك لا نقرأ الطالع من البرج فقط، بل من نوعية الحد أيضًا؛ فالحد يوضح طريقة خروج الطاقة إلى الحياة."
    )

    for key in ["Sun", "Moon", "Mercury", "Venus", "Mars"]:
        p = positions[key]
        items.append(
            f"{p.name_ar} في حد {p.term}: {TERM_INTERPRETATION.get(p.term or '', '')} "
            f"هذا يلوّن دلالة {p.name_ar} داخل {p.sign} ويجعل أثره في البيت {p.house} أكثر تحديدًا."
        )

    return items


def generate_supporting_techniques(positions, cusps, angles, aspects, element_scores) -> List[str]:
    """
    قسم يضم التقنيات التي اتفقنا على عدم إهمالها في V1:
    العناصر، الطبائع، الزوايا، البيوت الزاوية، حكام البيوت، الحدود.
    التقنيات الزمنية مثل التقدم والقوس الشمسي والعودة الشمسية تؤجل لنسخة التوقعات.
    """
    items: List[str] = []

    dominant_element = strongest_element(element_scores)
    items.append(
        f"العنصر الغالب هو {dominant_element}. هذا يحدد المزاج العام للطاقة: "
        "النار تدفع للمبادرة، التراب للبناء العملي، الهواء للفكر والتواصل، والماء للحدس والشعور."
    )

    modes = modality_scores(positions)
    dominant_mode = max(modes, key=lambda k: modes[k])
    mode_text = {
        "مبادر": "غلبة الطبيعة المبادرة تعني أن الطاقة تتحرك عبر البدء وفتح المسارات، لكنها تحتاج إلى إكمال ما تبدأه.",
        "ثابت": "غلبة الطبيعة الثابتة تعني قدرة على الصبر والاستمرار، لكنها تحتاج إلى مرونة أمام التغيير.",
        "متغير": "غلبة الطبيعة المتغيرة تعني قابلية للتكيّف والفهم السريع، لكنها تحتاج إلى تقليل التشتت."
    }
    items.append(f"الطبيعة الغالبة هي {dominant_mode}. {mode_text.get(dominant_mode, '')}")

    # البيوت الزاوية
    angular_planets = []
    for p in positions.values():
        if p.house in [1, 4, 7, 10]:
            angular_planets.append(f"{p.name_ar} في البيت {p.house}")
    if angular_planets:
        items.append(
            "الكواكب الموجودة في البيوت الزاوية تعطي تأثيرًا ظاهرًا وقويًا في الحياة. "
            "في هذه الخريطة يظهر: " + "، ".join(angular_planets[:8]) + "."
        )
    else:
        items.append(
            "لا توجد كواكب كثيرة في البيوت الزاوية، لذلك قد تعمل الشخصية بطريقة داخلية أو تدريجية أكثر من الظهور المباشر."
        )

    # حكام المحاور
    asc_sign = str(angles["ASC_sign"])
    desc_lon = normalize_deg(float(angles["ASC"]) + 180)
    desc_sign, desc_deg = sign_from_lon(desc_lon)
    mc_sign = str(angles["MC_sign"])
    ic_lon = normalize_deg(float(angles["MC"]) + 180)
    ic_sign, ic_deg = sign_from_lon(ic_lon)

    items.append(
        f"محور الأول والسابع: الطالع في {asc_sign} وحاكمه {SIGN_RULERS.get(asc_sign, '')}، "
        f"والهابط في {desc_sign} وحاكمه {SIGN_RULERS.get(desc_sign, '')}. "
        "هذا المحور يشرح التوازن بين الذات والآخر، وبين المبادرة الشخصية ونوع العلاقات التي تجذبها الخريطة."
    )

    items.append(
        f"محور الرابع والعاشر: الرابع في {ic_sign} وحاكمه {SIGN_RULERS.get(ic_sign, '')}، "
        f"والعاشر في {mc_sign} وحاكمه {SIGN_RULERS.get(mc_sign, '')}. "
        "هذا المحور يوضح العلاقة بين الجذور والعائلة من جهة، والطموح والسمعة والمهنة من جهة أخرى."
    )

    # الزوايا
    hard = [x for x in aspects if x[2] in ["تربيع", "مقابلة"]]
    soft = [x for x in aspects if x[2] in ["تثليث", "تسديس"]]
    conj = [x for x in aspects if x[2] == "اقتران"]

    if conj:
        items.append(
            "الاقترانات في الخريطة تعمل كمراكز تركيز قوية، لأنها تجمع طاقتين في نقطة واحدة. "
            "أبرزها: " + "، ".join([f"{a} مع {b}" for a, b, asp, orb in conj[:5]]) + "."
        )
    if hard:
        items.append(
            "التربيعات والمقابلات تمثل مناطق ضغط وتحدٍّ، لكنها أيضًا مناطق نضج وإنجاز إذا وُجهت بوعي. "
            "أبرزها: " + "، ".join([f"{a} {asp} {b}" for a, b, asp, orb in hard[:5]]) + "."
        )
    if soft:
        items.append(
            "التثليثات والتسديسات تمثل مواهب ومنافذ مساعدة، لكنها تحتاج إلى استخدام فعلي حتى لا تبقى طاقة كامنة. "
            "أبرزها: " + "، ".join([f"{a} {asp} {b}" for a, b, asp, orb in soft[:5]]) + "."
        )

    # ملاحظة تقنية زمنية
    items.append(
        "التقنيات الزمنية مثل التقدم الثانوي، القوس الشمسي، العودة الشمسية، العودة القمرية، البروفكشن والفريدار "
        "ليست مهملة، لكنها تُستخدم عند طلب توقيت أو توقع لفترة محددة، أما هنا فالمحور الأساسي هو قراءة الميلاد."
    )

    return items


def generate_dignity_summary(positions: Dict[str, BodyPosition]) -> List[str]:
    """
    خلاصة مرتبة لقوة الكواكب حسب الدستورية، مع انعكاسها على الشخصية.
    """
    rows = []
    key_by_name = {}
    for key in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]:
        p = positions[key]
        info = planet_constitution_analysis(key, p)
        rows.append((int(info["score"]), p.name_ar, info["level"], p.sign, p.house, key, info["reflection"]))
        key_by_name[p.name_ar] = key

    rows.sort(key=lambda x: x[0], reverse=True)

    strongest = rows[:3]
    weakest = rows[-3:]

    items = []
    items.append(
        "أقوى الكواكب دستوريًا في هذه الخريطة: "
        + "، ".join([f"{name} ({level})" for score, name, level, sign, house, key, reflection in strongest])
        + ". انعكاس ذلك على الشخصية أن هذه الكواكب تمثل أدوات طبيعية يمكن الاعتماد عليها في الثقة، الإنجاز، اتخاذ القرار، أو بناء العلاقات بحسب طبيعة كل كوكب."
    )
    items.append(
        "أكثر الكواكب حاجة إلى وعي أو تهذيب: "
        + "، ".join([f"{name} ({level})" for score, name, level, sign, house, key, reflection in weakest])
        + ". انعكاس ذلك لا يعني ضعفًا نهائيًا، بل يدل على مناطق قد يظهر فيها توتر أو تأخير أو حساسية، وتحتاج إلى تدريب وبيئة مناسبة."
    )

    for score, name, level, sign, house, key, reflection in rows:
        items.append(
            f"{name}: {level}، لأنه في {sign} والبيت {house}. الدرجة الدستورية: {score}. {reflection}"
        )

    return items


# ============================================================
# أنماط توزيع الكواكب في الخريطة
# Bundle / Bowl / Bucket / Splash / Seesaw / Locomotive / Splay
# ============================================================

PATTERN_AR_NAMES = {
    "Bundle": "الحزمة",
    "Bowl": "الوعاء",
    "Bucket": "الدلو",
    "Splash": "الرش",
    "Seesaw": "الأرجوحة",
    "Locomotive": "القاطرة",
    "Splay": "التفرّع",
    "Mixed_Seesaw_Splay": "تفرّع مع ميل إلى الأرجوحة",
    "Mixed_Locomotive_Splay": "تفرّع مع ميل إلى القاطرة",
}

PATTERN_MEANINGS = {
    "Bundle": {
        "meaning": "هذا النمط يدل على أن الطاقة مركّزة في مساحة محددة من الخريطة. الشخصية هنا تميل إلى التعمق والتركيز في مجال أو اتجاه واضح.",
        "strength": "قوة هذا النمط في التركيز، العمق، والقدرة على توجيه الجهد نحو موضوع محدد.",
        "challenge": "تحديه أن لا تنحصر الحياة في زاوية واحدة، وأن لا يتحول التركيز إلى انغلاق أو ضيق في الرؤية.",
        "advice": "النصيحة: استفد من قوة التركيز، لكن افتح لنفسك نوافذ جديدة حتى لا تبقى الطاقة محصورة في مجال واحد."
    },
    "Bowl": {
        "meaning": "هذا النمط يدل على أن الكواكب متجمعة في نصف الخريطة تقريبًا، وكأن هناك نصفًا ممتلئًا ونصفًا ينتظر الاكتمال. الشخصية تشعر غالبًا بوجود جانب ناقص تسعى إلى تعويضه أو فهمه.",
        "strength": "قوته في الوعي بما يملكه الفرد وبناء موقف واضح من الحياة.",
        "challenge": "تحديه هو الشعور الداخلي بالنقص أو السعي المستمر نحو الجهة الفارغة من الخريطة.",
        "advice": "النصيحة: لا تنظر إلى الجهة الفارغة كعجز، بل كمساحة نمو وتعلّم وتجربة."
    },
    "Bucket": {
        "meaning": "هذا النمط يدل على أن أغلب الكواكب متجمعة في جهة، مع كوكب منفرد في الجهة المقابلة يعمل مثل مقبض الدلو. هذا الكوكب يصبح مفتاحًا مهمًا في توجيه الحياة.",
        "strength": "قوته في وجود كوكب موجّه يركز طاقة الخريطة ويعطيها بوابة واضحة للتعبير.",
        "challenge": "تحديه أن لا تصبح حياة الفرد كلها معلّقة بموضوع الكوكب المنفرد فقط.",
        "advice": "النصيحة: استخدم الكوكب المقبض كأداة توجيه، لا كعبء أو نقطة تعلق."
    },
    "Splash": {
        "meaning": "هذا النمط يدل على انتشار الكواكب في معظم أجزاء الخريطة. الشخصية متعددة الاهتمامات وقادرة على تجربة أكثر من مجال.",
        "strength": "قوته في التنوع، المرونة، والانفتاح على خبرات مختلفة.",
        "challenge": "تحديه هو التشتت وصعوبة تثبيت الجهد في مسار واحد لفترة كافية.",
        "advice": "النصيحة: اجعل التنوع مصدر غنى، لكن اختر أولويات واضحة حتى لا تتوزع الطاقة بلا نتيجة."
    },
    "Seesaw": {
        "meaning": "هذا النمط يدل على وجود مجموعتين متقابلتين من الكواكب. الحياة تُعاش غالبًا عبر شدّ بين طرفين أو محورين.",
        "strength": "قوته في القدرة على رؤية الجانبين والمقارنة والموازنة.",
        "challenge": "تحديه هو التردد أو الشعور بأنه ممزق بين اتجاهين: الذات والآخر، العمل والعائلة، العقل والعاطفة، أو الحرية والمسؤولية.",
        "advice": "النصيحة: لا تجعل التناقض صراعًا دائمًا؛ حوّله إلى قدرة على التوازن والاختيار الواعي."
    },
    "Locomotive": {
        "meaning": "هذا النمط يدل على انتشار الكواكب في معظم الخريطة مع فراغ كبير واحد، وكأن هناك قوة دفع تتحرك باتجاه واضح.",
        "strength": "قوته في الاندفاع، فتح الطريق، والاستمرار في الحركة نحو هدف.",
        "challenge": "تحديه هو التسرع أو الشعور الدائم بأنه يجب أن يدفع الحياة إلى الأمام.",
        "advice": "النصيحة: حدّد الهدف قبل الاندفاع، لأن قوة القاطرة تصبح أعظم عندما تعرف إلى أين تتجه."
    },
    "Splay": {
        "meaning": "هذا النمط يدل على وجود عدة تجمعات للكواكب بصورة غير منتظمة. الشخصية لها أكثر من مركز اهتمام وقد لا تسير في خط واحد.",
        "strength": "قوته في الأصالة والاستقلال والقدرة على العمل في أكثر من محور.",
        "challenge": "تحديه هو صعوبة جمع المسارات المختلفة في هوية واحدة أو هدف واضح.",
        "advice": "النصيحة: لا تحارب تعدد اهتماماتك، لكن امنحه نظامًا حتى يتحول إلى مشروع واضح."
    },
    "Mixed_Seesaw_Splay": {
        "meaning": "هذا النمط يدل على وجود أكثر من تجمع كوكبي مع شدّ واضح بين جهتين، لكنه لا يصل إلى أرجوحة صافية لأن المجموعات غير متوازنة.",
        "strength": "قوته في القدرة على رؤية أكثر من زاوية، مع تعدد مراكز الاهتمام والخبرة.",
        "challenge": "تحديه هو أن يشعر الفرد بشدّ بين محورين، لكنه في الوقت نفسه لا يملك توازن الأرجوحة الكلاسيكية؛ لذلك قد يتنقل بين أكثر من مركز ضغط أو اهتمام.",
        "advice": "النصيحة: لا تتعامل مع التناقض كصراع دائم، ولا مع التعدد كتشتت؛ اجمع المحاور المختلفة في هدف عملي واضح."
    },
    "Mixed_Locomotive_Splay": {
        "meaning": "هذا النمط يدل على وجود قوة دفع واضحة بسبب فراغ كبير، لكن التوزيع الداخلي للكواكب ليس متصلًا بما يكفي ليكون قاطرة صافية.",
        "strength": "قوته في وجود دافع للتقدم مع أكثر من مركز اهتمام.",
        "challenge": "تحديه هو التذبذب بين الاندفاع نحو هدف وبين التوزع على أكثر من اتجاه.",
        "advice": "النصيحة: حدّد مركز القيادة أولًا، ثم رتّب بقية الاهتمامات حوله حتى لا تتبعثر الطاقة."
    },
}

PLANET_LEADER_MEANINGS = {
    "الشمس": "الكوكب القائد هنا يشير إلى أن الإرادة والهوية والظهور هي بوابة الحركة في الحياة.",
    "القمر": "الكوكب القائد هنا يشير إلى أن الشعور والحاجة إلى الأمان والذاكرة النفسية تقود كثيرًا من الاستجابات.",
    "عطارد": "الكوكب القائد هنا يشير إلى أن التفكير والكلام والتعلم والربط الذهني هي بوابة الحركة.",
    "الزهرة": "الكوكب القائد هنا يشير إلى أن العلاقات والقبول والذوق والمال اللطيف لها دور محوري في توجيه الحياة.",
    "المريخ": "الكوكب القائد هنا يشير إلى أن المبادرة والفعل والمواجهة والجرأة هي مفاتيح أساسية في الشخصية.",
    "المشتري": "الكوكب القائد هنا يشير إلى أن التوسع والمعرفة والسفر والثقة والفرص تقود مسارًا مهمًا في الحياة.",
    "زحل": "الكوكب القائد هنا يشير إلى أن المسؤولية والصبر والبناء والخوف من الفشل أو الرغبة في الإنجاز تشكل محورًا مهمًا.",
    "أورانوس": "الكوكب القائد هنا يشير إلى أن الاستقلال والتغيير والاختلاف والتحرر من النمط التقليدي يوجهان الخريطة.",
    "نبتون": "الكوكب القائد هنا يشير إلى أن الخيال والحدس والروحانية والغموض والإلهام لهم تأثير واضح في الحركة الداخلية.",
    "بلوتو": "الكوكب القائد هنا يشير إلى أن التحول العميق والقوة والسيطرة الواعية وإعادة البناء بعد الأزمات تقود جزءًا مهمًا من الحياة.",
}


PATTERN_LIFE_REFLECTIONS = {
    "Bundle": (
        "الشرح العملي للقارئ: عندما تكون الخريطة من نوع الحزمة فهذا يعني أن الطاقة النفسية والحياتية مركزة في قطاع محدود من الحياة. "
        "صاحب هذه الخريطة غالبًا لا يعيش كل شيء بالتساوي، بل ينشد مجالًا محددًا يغرق فيه أو يتخصص به أو يشعر أنه يمثل مركز حياته. "
        "هذا يعطي قوة تركيز عالية وقدرة على التعمق، لكنه قد يجعل الشخص يرى الحياة من زاوية واحدة فقط. "
        "مفتاح النمو هنا هو توسيع التجربة دون خسارة قوة التركيز."
    ),
    "Bowl": (
        "الشرح العملي للقارئ: نمط الوعاء يعني أن هناك نصفًا ممتلئًا من الخريطة ونصفًا يبدو فارغًا، ولذلك يشعر الشخص غالبًا أن لديه جانبًا قويًا يعرفه جيدًا، "
        "وفي المقابل يوجد جانب آخر يبحث عنه أو يحاول تعويضه. "
        "هذا النمط يعطي وعيًا واضحًا بالذات وبما يملكه الفرد، لكنه قد يخلق شعورًا داخليًا بأن شيئًا ما ناقص أو أن الحياة تطلب منه الوصول إلى الجهة الأخرى. "
        "مفتاح النمو هنا هو عدم التعامل مع الفراغ كضعف، بل كاتجاه تطور."
    ),
    "Bucket": (
        "الشرح العملي للقارئ: نمط الدلو يعني أن الخريطة كلها تقريبًا تصب طاقتها في كوكب واحد منفرد يسمى المقبض. "
        "هذا الكوكب يصبح بوابة التعبير عن الخريطة كلها؛ من خلاله يتحرك الشخص، ومن خلال رمزيته يفرغ الضغط أو يوجه حياته. "
        "إذا نضج هذا الكوكب أصبح أداة قيادة وتركيز، وإذا لم ينضج قد يتحول إلى نقطة تعلق أو رد فعل زائد. "
        "مفتاح النمو هنا هو فهم الكوكب المقبض واستعماله بوعي بدل أن يقود الشخصية بصورة لا إرادية."
    ),
    "Splash": (
        "الشرح العملي للقارئ: نمط الرش يعني أن الكواكب منتشرة في أجزاء واسعة من الخريطة، ولذلك يكون الشخص متعدد الاهتمامات والتجارب. "
        "قد يملك قابلية للتعامل مع أكثر من مجال وأكثر من نوع من الناس، ولا يحب أن يُحصر في اتجاه واحد فقط. "
        "قوة هذا النمط في التنوع والمرونة والانفتاح، أما تحديه فهو التشتت أو صعوبة اختيار أولوية واحدة. "
        "مفتاح النمو هنا هو تحويل التعدد إلى شبكة خبرات منظمة لا إلى طاقة مبعثرة."
    ),
    "Seesaw": (
        "الشرح العملي للقارئ: نمط الأرجوحة يعني أن الحياة تُعاش غالبًا بين قطبين واضحين. "
        "الشخص يرى الأشياء من جهتين، ويشعر أحيانًا أنه مطالب بالموازنة بين اتجاهين متعارضين: الذات والآخر، البيت والعمل، العقل والعاطفة، الحرية والمسؤولية. "
        "قوة هذا النمط في القدرة على المقارنة ورؤية الجانبين، أما تحديه فهو التردد أو الشعور بالانقسام. "
        "مفتاح النمو هنا هو تحويل الشد الداخلي إلى مهارة في التوازن لا إلى صراع دائم."
    ),
    "Locomotive": (
        "الشرح العملي للقارئ: نمط القاطرة يعني أن هناك قوة دفع واضحة في الخريطة. "
        "الشخص يشعر غالبًا أنه يجب أن يتحرك أو يفتح الطريق أو يتقدم نحو هدف. "
        "الكوكب القائد هنا مهم جدًا لأنه يوضح كيف تبدأ الحركة: هل تبدأ بالفعل، بالكلام، بالمسؤولية، بالعاطفة، أو بالرؤية؟ "
        "قوة هذا النمط في الاندفاع والاستمرار، أما تحديه فهو التسرع أو الشعور الدائم بالضغط. "
        "مفتاح النمو هنا هو تحديد الوجهة قبل استخدام قوة الدفع."
    ),
    "Splay": (
        "الشرح العملي للقارئ: نمط التفرّع يعني أن الخريطة لا تتحرك من مركز واحد فقط، بل من عدة مراكز اهتمام. "
        "الشخص قد يكون مستقلًا وغير تقليدي، يجمع بين مجالات مختلفة أو يعيش مراحل متباينة في حياته. "
        "قوة هذا النمط في الأصالة وتعدد الموارد الداخلية، أما تحديه فهو صعوبة جمع هذه المسارات في هوية واحدة أو مشروع واضح. "
        "مفتاح النمو هنا هو بناء خيط ناظم يجمع الاهتمامات بدل تركها متفرقة."
    ),
    "Mixed_Seesaw_Splay": (
        "الشرح العملي للقارئ: هذا نمط مختلط بين التفرّع والأرجوحة. "
        "يوجد شد بين جهتين، لكن المجموعات ليست متوازنة بما يكفي لنقول إنها أرجوحة صافية. "
        "هذا يعني أن الشخص قد يشعر بتناقض أو سحب بين محورين، لكنه في الوقت نفسه يملك أكثر من مركز اهتمام وليس قطبين فقط. "
        "مفتاح النمو هنا هو عدم تبسيط الحياة إلى طرفين متصارعين، بل فهم المحاور المتعددة وتنظيمها."
    ),
    "Mixed_Locomotive_Splay": (
        "الشرح العملي للقارئ: هذا نمط مختلط بين القاطرة والتفرّع. "
        "هناك قوة دفع وفراغ واضح في الخريطة، لكن الكواكب ليست متصلة بما يكفي لتكون قاطرة صافية. "
        "هذا يعني أن الشخص يملك اندفاعًا نحو هدف، لكنه قد يتوزع في الوقت نفسه على أكثر من مسار. "
        "مفتاح النمو هنا هو اختيار مركز قيادة واضح ثم ترتيب بقية الاهتمامات حوله."
    ),
}


PLANET_HANDLE_REFLECTIONS = {
    "الشمس": (
        "لأن الشمس هي الكوكب المحوري هنا، فإن مفتاح الخريطة هو بناء الهوية والثقة والقدرة على الظهور. "
        "عندما يعرف الشخص من يكون وماذا يريد أن يترك من أثر، تتنظم بقية طاقته. "
        "التحدي هو ألا يربط قيمته كلها بالاعتراف أو الإعجاب."
    ),
    "القمر": (
        "لأن القمر هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الأمان النفسي وإدارة المشاعر. "
        "الحياة تتحرك بقوة عندما يشعر الشخص بأنه محتوى ومطمئن. "
        "التحدي هو ألا تتحول الحاجة إلى الأمان إلى خوف أو تعلق أو تقلب مزاجي."
    ),
    "عطارد": (
        "لأن عطارد هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو التفكير والكلام والتعلم وربط المعلومات. "
        "الشخص يوجه حياته عبر الفهم، السؤال، التواصل، أو التحليل. "
        "التحدي هو ألا تتحول كثرة التفكير إلى تشتت أو قلق أو كلام غير محسوب."
    ),
    "الزهرة": (
        "لأن الزهرة هي الكوكب المحوري هنا، فإن مفتاح الخريطة هو العلاقات والقبول والذوق والقيمة والمال اللطيف. "
        "الشخص يفتح أبوابه غالبًا عبر الانسجام أو الجمال أو المحبة أو القدرة على جذب الناس. "
        "التحدي هو ألا تصبح قيمته معلقة بقبول الآخرين أو الخوف من الرفض."
    ),
    "المريخ": (
        "لأن المريخ هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الفعل والمبادرة والدفاع وإدارة الغضب. "
        "الشخص لا يخرج من الضغط بالكلام فقط، بل يحتاج إلى حركة وقرار وفعل واضح. "
        "إذا نضج المريخ تحولت الحساسية أو التوتر إلى شجاعة وإنجاز، وإذا لم ينضج قد يظهر كاندفاع أو رد فعل دفاعي."
    ),
    "المشتري": (
        "لأن المشتري هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الثقة والمعرفة والتوسع والفرص. "
        "الشخص يتحرك عندما يرى معنى أكبر أو أفقًا أوسع. "
        "التحدي هو ألا تتحول الثقة إلى مبالغة، أو الوعد إلى توسع بلا خطة."
    ),
    "زحل": (
        "لأن زحل هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو المسؤولية والصبر والبناء الطويل. "
        "الشخص يتحرك عندما يشعر أن عليه واجبًا أو هدفًا يستحق الالتزام. "
        "التحدي هو ألا يتحول الالتزام إلى ثقل دائم أو خوف من الفشل."
    ),
    "أورانوس": (
        "لأن أورانوس هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو التحرر والاختلاف والابتكار. "
        "الشخص يتحرك عندما يشعر أنه يستطيع كسر النمط أو فتح طريق جديد. "
        "التحدي هو ألا تتحول الحرية إلى قطيعة أو تمرد بلا اتجاه."
    ),
    "نبتون": (
        "لأن نبتون هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الخيال والحدس والإلهام والروحانية. "
        "الشخص يتحرك من الصورة الداخلية أو الإحساس الخفي أكثر من المنطق المباشر. "
        "التحدي هو ألا يتحول الإلهام إلى ضبابية أو تعلق بصورة غير واقعية."
    ),
    "بلوتو": (
        "لأن بلوتو هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو التحول العميق والقوة الداخلية وكشف الخفي. "
        "الشخص يتحرك بقوة في الأزمات وعند الحاجة لإعادة البناء. "
        "التحدي هو ألا تتحول القوة إلى سيطرة أو خوف من الفقد."
    ),
}


def pattern_life_reflection(pattern: str, leader_name: str = "") -> str:
    """
    شرح حياتي مباشر لنمط الخريطة، مع شرح الكوكب المقبض أو القائد إن وجد.
    """
    base = PATTERN_LIFE_REFLECTIONS.get(pattern, PATTERN_LIFE_REFLECTIONS["Splay"])
    if leader_name:
        handle_text = PLANET_HANDLE_REFLECTIONS.get(leader_name, "")
        if handle_text:
            return base + " " + handle_text
    return base



def sorted_planet_points(positions: Dict[str, BodyPosition]) -> List[Tuple[float, str, str]]:
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    pts = []
    for key in order:
        p = positions[key]
        pts.append((normalize_deg(p.lon), key, p.name_ar))
    pts.sort(key=lambda x: x[0])
    return pts


def circular_gaps(points: List[Tuple[float, str, str]]) -> List[Dict[str, object]]:
    gaps = []
    n = len(points)
    for i in range(n):
        current_lon, current_key, current_ar = points[i]
        next_lon, next_key, next_ar = points[(i + 1) % n]
        gap = normalize_deg(next_lon - current_lon)
        gaps.append({
            "gap": gap,
            "from": points[i],
            "to": points[(i + 1) % n],
            "index": i,
        })
    gaps.sort(key=lambda x: float(x["gap"]), reverse=True)
    return gaps


def minimal_arc_span(points: List[Tuple[float, str, str]]) -> Tuple[float, Dict[str, object]]:
    """
    أصغر قوس يحتوي كل الكواكب = 360 - أكبر فراغ.
    """
    gaps = circular_gaps(points)
    largest = gaps[0]
    span = 360.0 - float(largest["gap"])
    return span, largest


def arc_span_for_subset(subset: List[Tuple[float, str, str]]) -> float:
    """
    أصغر قوس يحتوي مجموعة كواكب معينة.
    """
    if len(subset) <= 1:
        return 0.0
    subset_sorted = sorted(subset, key=lambda x: x[0])
    gaps = circular_gaps(subset_sorted)
    largest = gaps[0]
    return 360.0 - float(largest["gap"])


def split_clusters(points: List[Tuple[float, str, str]], gap_threshold: float = 60.0) -> List[List[Tuple[float, str, str]]]:
    """
    تقسيم الكواكب إلى تجمعات حسب الفراغات الكبيرة.
    نبدأ من بعد أكبر فراغ حتى لا ينكسر التجمع عند 0°.
    """
    if not points:
        return []

    pts = sorted(points, key=lambda x: x[0])
    gaps_original = []
    n = len(pts)
    for i in range(n):
        gap = normalize_deg(pts[(i + 1) % n][0] - pts[i][0])
        gaps_original.append((gap, i))

    # البداية من بعد أكبر فراغ
    largest_gap_index = max(gaps_original, key=lambda x: x[0])[1]
    ordered = pts[largest_gap_index + 1:] + pts[:largest_gap_index + 1]

    clusters: List[List[Tuple[float, str, str]]] = [[ordered[0]]]
    for i in range(len(ordered) - 1):
        gap = normalize_deg(ordered[i + 1][0] - ordered[i][0])
        if gap >= gap_threshold:
            clusters.append([ordered[i + 1]])
        else:
            clusters[-1].append(ordered[i + 1])

    return clusters


def occupied_sign_count(points: List[Tuple[float, str, str]]) -> int:
    return len(set(int(p[0] // 30) for p in points))


def find_bucket_handle(points: List[Tuple[float, str, str]]) -> Optional[Tuple[float, str, str]]:
    """
    قاعدة مشددة للدلو Bucket:
    - 9 كواكب تقريبًا يجب أن تكون داخل كتلة واحدة واضحة.
    - الكوكب العاشر منفرد بوضوح عن طرفي الكتلة.
    - لا نقبل Bucket إذا كانت هناك كتلتان واضحتان أو أكثر.
    """
    candidates = []

    for candidate in points:
        others = [p for p in points if p != candidate]
        others_span = arc_span_for_subset(others)

        # التسعة الباقية يجب أن تكون ضمن نصف الخريطة تقريبًا.
        if others_span > 190:
            continue

        all_sorted = sorted(points, key=lambda x: x[0])
        idx = all_sorted.index(candidate)
        prev_pt = all_sorted[(idx - 1) % len(all_sorted)]
        next_pt = all_sorted[(idx + 1) % len(all_sorted)]

        left_gap = normalize_deg(candidate[0] - prev_pt[0])
        right_gap = normalize_deg(next_pt[0] - candidate[0])

        # المقبض الحقيقي يجب أن يكون واضح العزلة من الجهتين.
        if min(left_gap, right_gap) < 40:
            continue
        if left_gap + right_gap < 125:
            continue

        # نتأكد أن التسعة ليست مقسمة إلى أكثر من كتلة كبيرة.
        other_clusters = split_clusters(others, gap_threshold=60)
        if len([c for c in other_clusters if len(c) >= 2]) > 1:
            continue

        score = (190 - others_span) + (left_gap + right_gap)
        candidates.append((score, candidate))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return None


def leading_planet_after_gap(largest_gap: Dict[str, object]) -> Tuple[float, str, str]:
    """
    الكوكب القائد في القاطرة هو أول كوكب بعد الفراغ الكبير.
    """
    return largest_gap["to"]  # type: ignore


def classify_chart_pattern(positions: Dict[str, BodyPosition]) -> Dict[str, object]:
    """
    تصنيف شامل لأنماط الخرائط:
    Bundle, Bowl, Bucket, Splash, Seesaw, Locomotive, Splay.

    الفكرة:
    - Bundle: كل الكواكب داخل 120° أو أقل.
    - Bowl: كل الكواكب داخل نصف الخريطة تقريبًا، بدون مقبض منفرد.
    - Bucket: 9 كواكب في كتلة + كوكب منفرد حقيقي.
    - Splash: انتشار واسع بلا فجوات كبيرة.
    - Seesaw: مجموعتان واضحتان يفصل بينهما فراغان كبيران، وكل مجموعة فيها كوكبان أو أكثر.
    - Locomotive: انتشار على نحو 240° مع فراغ كبير واحد، بدون انقسام إلى مجموعتين واضحتين.
    - Splay: ثلاث تجمعات أو توزيع غير منتظم لا ينطبق عليه ما سبق.
    """
    points = sorted_planet_points(positions)
    gaps = circular_gaps(points)
    span, largest_gap = minimal_arc_span(points)
    largest_gap_value = float(largest_gap["gap"])
    second_gap_value = float(gaps[1]["gap"]) if len(gaps) > 1 else 0.0
    signs_count = occupied_sign_count(points)

    clusters_60 = split_clusters(points, gap_threshold=60)
    clusters_50 = split_clusters(points, gap_threshold=50)
    strong_clusters = [c for c in clusters_60 if len(c) >= 2]

    cluster_sizes = sorted([len(c) for c in strong_clusters], reverse=True)
    seesaw_balanced = False
    if len(cluster_sizes) == 2:
        smaller = min(cluster_sizes)
        larger = max(cluster_sizes)
        # الأرجوحة الصافية تحتاج مجموعتين معتبرتين ومتقاربتين نسبيًا.
        # 2 مقابل 8 ليست أرجوحة صافية.
        seesaw_balanced = smaller >= 3 and (larger / smaller) <= 2.25

    handle = find_bucket_handle(points)
    pattern = "Splay"
    leader = None
    confidence = "متوسط"

    # 1) الحزمة: تركيز شديد.
    if span <= 120:
        pattern = "Bundle"
        confidence = "عالٍ"

    # 2) الدلو: لا يُقبل إلا بمقبض حقيقي.
    elif handle is not None:
        pattern = "Bucket"
        leader = handle
        confidence = "عالٍ"

    # 3) الوعاء: كل الكواكب في نصف الخريطة تقريبًا.
    elif span <= 195:
        pattern = "Bowl"
        confidence = "عالٍ" if span <= 185 else "متوسط"

    # 4) الرش: انتشار واسع بلا فجوة كبرى وبعدد أبراج واسع.
    elif largest_gap_value < 70 and signs_count >= 7:
        pattern = "Splash"
        confidence = "عالٍ"

    # 5) الأرجوحة الصافية: مجموعتان واضحتان ومتقاربتان نسبيًا.
    elif len(strong_clusters) == 2 and seesaw_balanced and largest_gap_value >= 70 and second_gap_value >= 55:
        pattern = "Seesaw"
        confidence = "عالٍ" if second_gap_value >= 70 else "متوسط"

    # 5b) مجموعتان واضحتان لكن غير متوازنتين: تفرع مع ميل إلى الأرجوحة.
    elif len(strong_clusters) == 2 and not seesaw_balanced and largest_gap_value >= 70 and second_gap_value >= 55:
        pattern = "Mixed_Seesaw_Splay"
        confidence = "متوسط"

    # 6) القاطرة الصافية: فراغ كبير واحد وانتشار على ثلثي الخريطة تقريبًا، مع عدم وجود فراغ ثانٍ كبير.
    elif 205 <= span <= 285 and 75 <= largest_gap_value <= 155 and second_gap_value < 70:
        pattern = "Locomotive"
        leader = leading_planet_after_gap(largest_gap)
        confidence = "متوسط" if largest_gap_value < 90 or largest_gap_value > 140 else "عالٍ"

    # 6b) قاطرة غير صافية بسبب فراغ ثانٍ كبير: تفرع مع ميل إلى القاطرة.
    elif 205 <= span <= 285 and 75 <= largest_gap_value <= 155 and 70 <= second_gap_value < 90:
        pattern = "Mixed_Locomotive_Splay"
        leader = leading_planet_after_gap(largest_gap)
        confidence = "متوسط"

    # 7) إذا كانت هناك ثلاث كتل أو أكثر فهو تفرّع.
    elif len([c for c in clusters_50 if len(c) >= 2]) >= 3:
        pattern = "Splay"
        confidence = "عالٍ"

    # 8) الحالات المختلطة.
    else:
        pattern = "Splay"
        confidence = "متوسط"

    return {
        "points": points,
        "gaps": gaps,
        "span": span,
        "largest_gap": largest_gap,
        "largest_gap_value": largest_gap_value,
        "second_gap_value": second_gap_value,
        "clusters_60": clusters_60,
        "clusters_50": clusters_50,
        "strong_clusters": strong_clusters,
        "signs_count": signs_count,
        "handle": handle,
        "pattern": pattern,
        "leader": leader,
        "confidence": confidence,
    }

def pattern_reason(pattern: str, data: Dict[str, object]) -> str:
    span = float(data["span"])
    largest_gap_value = float(data["largest_gap_value"])
    second_gap_value = float(data["second_gap_value"])
    signs_count = int(data["signs_count"])
    strong_clusters = data["strong_clusters"]
    handle = data["handle"]

    if pattern == "Bundle":
        return f"لأن الكواكب كلها تقريبًا محصورة داخل قوس صغير قدره نحو {span:.0f} درجة، وهذا يدل على تركيز شديد للطاقة."
    if pattern == "Bowl":
        return f"لأن الكواكب تقع تقريبًا داخل نصف الخريطة أو قريبًا منه، مع فراغ كبير يقارب {largest_gap_value:.0f} درجة، ولا يوجد كوكب منفرد حقيقي يصلح كمقبض."
    if pattern == "Bucket" and handle:
        return f"لأن تسعة كواكب تقريبًا تتجمع في كتلة واحدة واضحة، مع كوكب منفرد هو {handle[2]} يعمل كمقبض حقيقي للخريطة."
    if pattern == "Splash":
        return f"لأن الكواكب منتشرة في أغلب أجزاء الخريطة، وتشغل نحو {signs_count} أبراج، ولا توجد فجوة كبرى تسيطر على التوزيع."
    if pattern == "Seesaw":
        sizes = sorted([len(c) for c in strong_clusters], reverse=True)  # type: ignore
        return f"لأن الكواكب منقسمة إلى مجموعتين واضحتين ومتقاربتين نسبيًا؛ المجموعة الأكبر تضم نحو {sizes[0]} كواكب، والأصغر تضم نحو {sizes[1]} كواكب، ويفصل بينهما فراغان كبيران."
    if pattern == "Mixed_Seesaw_Splay":
        sizes = sorted([len(c) for c in strong_clusters], reverse=True)  # type: ignore
        return f"لأن هناك مجموعتين واضحتين لكن غير متوازنتين؛ المجموعة الأكبر تضم نحو {sizes[0]} كواكب، والأصغر نحو {sizes[1]} كواكب، مع فراغين كبيرين. لذلك لا نعدّها أرجوحة صافية."
    if pattern == "Locomotive":
        return f"لأن الكواكب تنتشر على قوس واسع يقارب {span:.0f} درجة، مع فراغ كبير واحد يقارب {largest_gap_value:.0f} درجة، ولا توجد كتلتان متقابلتان واضحتان."
    if pattern == "Mixed_Locomotive_Splay":
        return f"لأن هناك فراغًا كبيرًا يعطي دفع القاطرة، لكن وجود فراغ ثانٍ معتبر يجعل التوزيع غير متصل تمامًا، لذلك لا نعدّها قاطرة صافية."
    return "لأن توزيع الكواكب غير منتظم أو مقسّم إلى عدة مراكز اهتمام، ولا تنطبق عليه شروط الحزمة أو الوعاء أو الدلو أو الرش أو الأرجوحة أو القاطرة بدقة."

def detect_chart_pattern(positions: Dict[str, BodyPosition]) -> Dict[str, object]:
    data = classify_chart_pattern(positions)

    pattern = str(data["pattern"])
    leader = data["leader"]
    ar_name = PATTERN_AR_NAMES.get(pattern, pattern)
    meaning = PATTERN_MEANINGS.get(pattern, PATTERN_MEANINGS["Splay"])

    reason = pattern_reason(pattern, data)
    leader_text = ""
    leader_name = ""
    if leader is not None:
        leader_name = leader[2]
        leader_text = (
            f"الكوكب القائد أو المحوري في هذا النمط هو {leader_name}. "
            + PLANET_LEADER_MEANINGS.get(leader_name, "")
        )

    confidence = data.get("confidence", "متوسط")
    life_reflection = pattern_life_reflection(pattern, leader_name)

    text = (
        f"نوع الخريطة: {ar_name} ({pattern}). "
        f"درجة الثقة في التصنيف: {confidence}. "
        f"{reason} "
        f"{meaning['meaning']} {meaning['strength']} {meaning['challenge']} "
        f"{leader_text} "
        f"{life_reflection} "
        f"{meaning['advice']}"
    )

    return {
        "pattern": pattern,
        "ar_name": ar_name,
        "span": round(float(data["span"]), 2),
        "largest_gap": round(float(data["largest_gap_value"]), 2),
        "second_gap": round(float(data["second_gap_value"]), 2),
        "clusters": len(data["clusters_60"]),  # type: ignore
        "occupied_signs": int(data["signs_count"]),
        "leader": leader[2] if leader is not None else "",
        "confidence": confidence,
        "text": text,
    }





# ============================================================
# تحليل الاتصالات الرئيسية
# ============================================================

ASPECT_NATURE = {
    "اقتران": "مركّز",
    "تربيع": "ضاغط",
    "مقابلة": "ضاغط",
    "تثليث": "داعم",
    "تسديس": "داعم",
}

ASPECT_BASE_MEANING = {
    "اقتران": "الاقتران يعني أن طاقتين تعملان في نقطة واحدة، لذلك يكون أثره قويًا ومركّزًا وقد يظهر كصفة واضحة في الشخصية.",
    "تربيع": "التربيع يدل على احتكاك داخلي أو ضغط يدفع إلى النمو. ليس سلبيًا بالضرورة، لكنه يحتاج إلى وعي حتى لا يتحول إلى توتر أو رد فعل.",
    "مقابلة": "المقابلة تدل على شدّ بين طرفين أو حاجتين متقابلتين. قوتها في الوعي بالآخر والتوازن، وتحديها في عدم العيش بين نقيضين دائمًا.",
    "تثليث": "التثليث يدل على موهبة أو انسجام طبيعي بين طاقتين. قوته أنه يسهل التعبير، وتحديه أن لا يبقى كسلًا أو طاقة غير مستثمرة.",
    "تسديس": "التسديس يدل على فرصة قابلة للتفعيل. لا يعمل دائمًا وحده، لكنه يعطي منفذًا جيدًا إذا بادر الشخص إلى استخدامه."
}

PLANET_PAIR_MEANINGS = {
    ("الشمس", "القمر"): "هذا الاتصال يربط الإرادة بالمشاعر، ويؤثر في التوازن بين ما يريده الشخص وما يحتاجه نفسيًا.",
    ("الشمس", "عطارد"): "هذا الاتصال يربط الهوية بالتفكير والكلام، وقد يعطي حضورًا ذهنيًا أو حاجة للتعبير عن الرأي.",
    ("الشمس", "الزهرة"): "هذا الاتصال يربط الهوية بالقبول والجمال والعاطفة، ويدعم الذوق والجاذبية والرغبة في الانسجام.",
    ("الشمس", "المريخ"): "هذا الاتصال يربط الإرادة بالفعل، ويزيد الشجاعة والمبادرة، لكنه يحتاج إلى تهذيب الاندفاع.",
    ("الشمس", "المشتري"): "هذا الاتصال يربط الهوية بالتوسع والثقة، وقد يعطي طموحًا ورغبة في النمو أو الظهور.",
    ("الشمس", "زحل"): "هذا الاتصال يعطي جدية ومسؤولية وإحساسًا مبكرًا بضرورة إثبات الذات. قوته في الصبر، وتحديه في القسوة على النفس.",
    ("الشمس", "أورانوس"): "هذا الاتصال يعطي استقلالًا ورغبة في الاختلاف وكسر النمط. قوته في الابتكار، وتحديه في التمرد أو عدم الثبات.",
    ("الشمس", "نبتون"): "هذا الاتصال يربط الهوية بالخيال والحدس، وقد يعطي إلهامًا وحسًا روحيًا، لكنه يحتاج إلى وضوح حتى لا يسبب ضبابية.",
    ("الشمس", "بلوتو"): "هذا الاتصال عميق وقوي، يدل على إرادة تحول وتجارب تعيد بناء الذات. قوته في العمق، وتحديه في السيطرة أو صراعات القوة.",

    ("القمر", "عطارد"): "هذا الاتصال يربط المشاعر بالتفكير والكلام، وقد يعطي قدرة على التعبير عن الإحساس أو تحليل المزاج.",
    ("القمر", "الزهرة"): "هذا الاتصال يدعم اللطف والقبول والحاجة إلى الحنان والانسجام العاطفي.",
    ("القمر", "المريخ"): "هذا الاتصال يزيد سرعة الانفعال ورد الفعل. قوته في الحماس والحماية، وتحديه في الغضب أو التسرع.",
    ("القمر", "المشتري"): "هذا الاتصال يعطي اتساعًا عاطفيًا وتعاطفًا وثقة، وقد يدعم الحماية والكرم النفسي.",
    ("القمر", "زحل"): "هذا الاتصال يعطي تحفظًا عاطفيًا أو شعورًا بالمسؤولية النفسية. قوته في النضج، وتحديه في الكتمان أو البرود الظاهري.",
    ("القمر", "أورانوس"): "هذا الاتصال يجعل المزاج سريع التغير أو مستقلًا. قوته في التحرر من الأنماط، وتحديه في التوتر وعدم الاستقرار.",
    ("القمر", "نبتون"): "هذا الاتصال يعطي حساسية وحدسًا وخيالًا، لكنه يحتاج إلى حدود نفسية واضحة حتى لا يسبب ذوبانًا أو مثالية.",
    ("القمر", "بلوتو"): "هذا الاتصال عميق نفسيًا، وقد يدل على مشاعر قوية وتجارب تحول. قوته في الشفاء، وتحديه في التعلق أو الخوف العميق.",

    ("عطارد", "الزهرة"): "هذا الاتصال يعطي لطفًا في الكلام وذوقًا في التعبير، ويفيد في الكتابة، الإقناع، الفن، أو التعليم اللطيف.",
    ("عطارد", "المريخ"): "هذا الاتصال يسرّع التفكير والكلام. قوته في الحسم، وتحديه في حدّة اللسان أو التسرع في الرد.",
    ("عطارد", "المشتري"): "هذا الاتصال يوسع التفكير ويدعم التعلم والسفر واللغات، لكنه يحتاج إلى عدم المبالغة أو التشتت.",
    ("عطارد", "زحل"): "هذا الاتصال يعطي عقلًا جادًا ومنهجيًا، وقد يفيد في البحث والتنظيم، لكنه قد يزيد القلق أو التردد في الكلام.",
    ("عطارد", "أورانوس"): "هذا الاتصال يعطي ذكاءً مفاجئًا وأفكارًا مختلفة، ويفيد في التقنية والابتكار والتحليل السريع.",
    ("عطارد", "نبتون"): "هذا الاتصال يعطي خيالًا وحدسًا في التفكير، لكنه يحتاج إلى تدقيق حتى لا تختلط الفكرة بالوهم أو سوء الفهم.",
    ("عطارد", "بلوتو"): "هذا الاتصال يعطي عمقًا فكريًا وقدرة على كشف الخفي، لكنه يحتاج إلى تجنب الهوس أو الشك الزائد.",

    ("الزهرة", "المريخ"): "هذا الاتصال يزيد الجاذبية والحركة العاطفية، ويربط الحب بالرغبة والفعل. يحتاج إلى تهذيب الانفعال داخل العلاقات.",
    ("الزهرة", "المشتري"): "هذا الاتصال يدعم القبول والكرم والفرص الاجتماعية أو المالية، لكنه يحتاج إلى ضبط المبالغة أو التوقعات العالية.",
    ("الزهرة", "زحل"): "هذا الاتصال يعطي جدية في الحب والمال، وقد يشير إلى تأخر أو تحفظ، لكنه يدعم العلاقات الناضجة إذا وُجد الصبر.",
    ("الزهرة", "أورانوس"): "هذا الاتصال يعطي ذوقًا مختلفًا وحاجة إلى حرية في العلاقات، لكنه قد يسبب مفاجآت أو عدم ثبات عاطفي.",
    ("الزهرة", "نبتون"): "هذا الاتصال يعطي رومانسية وخيالًا وفنًا، لكنه يحتاج إلى وضوح حتى لا تتحول المثالية إلى خيبة.",
    ("الزهرة", "بلوتو"): "هذا الاتصال يعطي عمقًا وجاذبية قوية في العلاقات، لكنه يحتاج إلى تجنب السيطرة أو التعلق الشديد.",

    ("المريخ", "المشتري"): "هذا الاتصال يزيد الجرأة والحماس والطاقة، وقد يدعم الإنجاز، لكنه يحتاج إلى خطة حتى لا يتحول إلى تهور.",
    ("المريخ", "زحل"): "هذا الاتصال يضع الفعل أمام الحدود. قوته في الصبر والعمل الشاق، وتحديه في الإحباط أو الغضب المكبوت.",
    ("المريخ", "أورانوس"): "هذا الاتصال يعطي اندفاعًا للتحرر وسرعة في الفعل، لكنه يحتاج إلى تجنب القرارات المفاجئة.",
    ("المريخ", "نبتون"): "هذا الاتصال يخلط الفعل بالخيال أو الحساسية، وقد يعطي إلهامًا في العمل، لكنه يحتاج إلى وضوح في الهدف.",
    ("المريخ", "بلوتو"): "هذا الاتصال قوي جدًا في الإرادة والتحول، وقد يعطي قدرة على المواجهة، لكنه يحتاج إلى ضبط القوة والسيطرة.",

    ("المشتري", "زحل"): "هذا الاتصال يوازن بين التوسع والحدود. قوته في بناء فرصة واقعية، وتحديه في الشد بين التفاؤل والخوف.",
    ("المشتري", "أورانوس"): "هذا الاتصال يعطي فرصًا مفاجئة ورغبة في التوسع والحرية، لكنه يحتاج إلى عدم التسرع.",
    ("المشتري", "نبتون"): "هذا الاتصال يعطي مثالية وإيمانًا وخيالًا واسعًا، لكنه يحتاج إلى تمييز بين الرؤية والحلم غير الواقعي.",
    ("المشتري", "بلوتو"): "هذا الاتصال يعطي طموحًا وقوة توسع وتأثير، لكنه يحتاج إلى أخلاق واضحة في استخدام النفوذ.",

    ("زحل", "أورانوس"): "هذا الاتصال يربط القديم بالجديد، وقد يخلق شدًا بين النظام والحرية. قوته في تحديث البنية دون هدمها.",
    ("زحل", "نبتون"): "هذا الاتصال يربط الحلم بالواقع، وقد يعطي قدرة على تجسيد الرؤية، لكنه يحتاج إلى عدم الاستسلام للغموض أو الإحباط.",
    ("زحل", "بلوتو"): "هذا الاتصال عميق وثقيل، يدل على اختبارات في القوة والصبر. قوته في إعادة البناء، وتحديه في الخوف أو التشدد.",

    ("أورانوس", "نبتون"): "هذا الاتصال جيلي غالبًا، ويدل على خيال مستقبلي وتغيير في الرؤية أو الوعي.",
    ("أورانوس", "بلوتو"): "هذا الاتصال جيلي غالبًا، ويدل على تغيير جذري ورغبة في التحرر والتحول.",
    ("نبتون", "بلوتو"): "هذا الاتصال جيلي غالبًا، ويدل على تحولات عميقة في الحس الروحي واللاوعي الجمعي."
}


def pair_key(a: str, b: str) -> Tuple[str, str]:
    """
    توحيد ترتيب أزواج الكواكب حسب ترتيب تقريبي من الأسرع/الشخصي إلى الأثقل.
    """
    order = {
        "الشمس": 1, "القمر": 2, "عطارد": 3, "الزهرة": 4, "المريخ": 5,
        "المشتري": 6, "زحل": 7, "أورانوس": 8, "نبتون": 9, "بلوتو": 10
    }
    return (a, b) if order.get(a, 99) <= order.get(b, 99) else (b, a)


def aspect_priority_score(a: str, b: str, asp: str, orb: float) -> float:
    """
    ترتيب الاتصالات المهمة: الأورب الأقل، والاتصالات الضاغطة/الاقتران، والكواكب الشخصية.
    """
    score = max(0.0, 10.0 - float(orb))

    if asp in ["اقتران", "تربيع", "مقابلة"]:
        score += 4
    elif asp in ["تثليث", "تسديس"]:
        score += 2

    personal = {"الشمس", "القمر", "عطارد", "الزهرة", "المريخ"}
    if a in personal:
        score += 2
    if b in personal:
        score += 2

    angles_like = {"الشمس", "القمر"}
    if a in angles_like or b in angles_like:
        score += 1.5

    return score


def aspect_reading_text(a: str, b: str, asp: str, orb: float) -> str:
    nature = ASPECT_NATURE.get(asp, "مؤثر")
    base = ASPECT_BASE_MEANING.get(asp, "")
    meaning = PLANET_PAIR_MEANINGS.get(pair_key(a, b), "هذا الاتصال يربط دلالتين مهمتين في الخريطة، ويُقرأ حسب طبيعة الكوكبين والبيت الذي يقع فيه كل منهما.")

    if nature == "ضاغط":
        advice = "النصيحة: لا تتعامل مع هذا الاتصال كعائق، بل كطاقة تحتاج إلى وعي وتنظيم حتى تتحول إلى نضج."
    elif nature == "داعم":
        advice = "النصيحة: هذه موهبة أو فرصة، لكنها تحتاج إلى استخدام عملي حتى لا تبقى كامنة."
    else:
        advice = "النصيحة: لأن هذا الاتصال مركّز، فمن المهم توجيهه بوعي حتى لا يطغى على بقية الشخصية."

    return (
        f"{a} {asp} {b} بفارق {orb:.2f}°. "
        f"نوع الاتصال: {nature}. {base} {meaning} {advice}"
    )


def generate_aspects_analysis(aspects) -> List[str]:
    """
    تحليل مختصر لأهم الاتصالات في الخريطة.
    لا نحلل كل الاتصالات حتى لا يطول التقرير، بل نختار الأهم.
    """
    if not aspects:
        return ["لا توجد اتصالات رئيسية واضحة ضمن الأورب المعتمد في هذه النسخة."]

    rows = []
    for a, b, asp, orb in aspects:
        rows.append((aspect_priority_score(a, b, asp, float(orb)), a, b, asp, float(orb)))

    rows.sort(key=lambda x: x[0], reverse=True)

    # نختار أهم 8 اتصالات كحد أعلى
    selected = rows[:8]
    return [aspect_reading_text(a, b, asp, orb) for score, a, b, asp, orb in selected]



# ============================================================
# جداول مواقع الكواكب والكويكبات والنقاط المهمة
# ============================================================

# كويكبات ونقاط إضافية مهمة للباحث الفلكي.
# بعضها حقيقي في Swiss Ephemeris، وبعض النقاط تُحسب عند توفرها.
ADDITIONAL_POINTS = [
    ("Chiron", "كايرون", "swe.CHIRON", True),
    ("Lilith", "ليليث", "swe.MEAN_APOG", False),
    ("NorthNode", "الرأس الشمالي", "swe.MEAN_NODE", False),
    ("SouthNode", "الذنب الجنوبي", "CALCULATED_SOUTH_NODE", False),
    ("Ceres", "سيريس", "swe.CERES", True),
    ("Pallas", "بالاس", "swe.PALLAS", True),
    ("Juno", "جونو", "swe.JUNO", True),
    ("Vesta", "فيستا", "swe.VESTA", True),
    ("Pholus", "فولو", "swe.PHOLUS", True),
]



IMPORTANT_POINT_MEANINGS = {
    "كايرون": {
        "core": "كايرون يمثل الجرح العميق الذي يتحول مع الوعي إلى حكمة وقدرة على الشفاء ومساعدة الآخرين.",
        "growth": "في قراءة النمو الذاتي، كايرون لا يُقرأ كضعف فقط، بل كمنطقة حساسة تحتاج إلى قبول ووعي حتى تتحول إلى موهبة علاجية أو فهم إنساني عميق."
    },
    "الرأس الشمالي": {
        "core": "العقدة الشمالية تمثل اتجاه النمو والتطور، أي الطريق الذي يدفع الشخص إلى الخروج من المألوف واكتساب خبرة جديدة.",
        "growth": "هي ليست سهلة دائمًا، لأنها تطلب من الشخص أن يتعلم سلوكًا جديدًا ويتقدم نحو منطقة غير معتادة في حياته."
    },
    "الذنب الجنوبي": {
        "core": "العقدة الجنوبية تمثل الخبرة القديمة أو النمط المألوف الذي يحمله الشخص بسهولة، لكنه قد يصبح منطقة تكرار أو ركود إذا بقي متعلقًا بها.",
        "growth": "المطلوب هنا ليس رفض الماضي، بل استخدامه كخبرة دون البقاء أسيرًا له."
    },
    "جونو": {
        "core": "جونو تمثل نمط الالتزام والشراكة والاحتياج إلى العدل داخل العلاقات العميقة أو الزواج.",
        "growth": "توضح ما الذي يحتاجه الشخص حتى يشعر أن العلاقة متوازنة ومحترمة، وما الذي قد يثير لديه حساسية تجاه الإهمال أو عدم الإنصاف."
    },
    "فيستا": {
        "core": "فيستا تمثل التركيز الداخلي، الإخلاص، الخدمة، والطاقة التي تحتاج إلى عزلة أو انضباط كي تبقى نقية ومثمرة.",
        "growth": "توضح أين يستطيع الشخص أن يكرّس نفسه بعمق، وأين يحتاج إلى حماية طاقته من الاستنزاف."
    },
    "بالاس": {
        "core": "بالاس تمثل الذكاء الاستراتيجي، حل المشكلات، قراءة الأنماط، والحكمة العملية في اتخاذ القرار.",
        "growth": "توضح الطريقة التي يفكر بها الشخص عندما يريد أن يحلل أو يخطط أو يجد حلًا ذكيًا بعيدًا عن الانفعال."
    },
    "فولو": {
        "core": "فولوس يمثل الشرارة الصغيرة التي قد تطلق سلسلة من الأحداث أو التحولات الكبيرة، لذلك يرتبط بردود الفعل المتسلسلة والنتائج غير المتوقعة.",
        "growth": "يوضح أين يجب الانتباه من قرارات بسيطة قد تفتح بابًا واسعًا، كما يوضح أين يمكن لخطوة صغيرة واعية أن تغيّر مسارًا كاملًا."
    },
    "سيريس": {
        "core": "سيريس تمثل الرعاية، التغذية، الاحتواء، العلاقة بالجسد والطعام، وطريقة العطاء أو استقبال العناية.",
        "growth": "توضح كيف يهتم الشخص بنفسه وبغيره، وأين يحتاج إلى توازن بين الرعاية وعدم استنزاف الذات."
    },
    "ليليث": {
        "core": "ليليث تمثل المنطقة البرية أو المكبوتة في النفس، وما قد يرفض الشخص الخضوع فيه أو يشعر أنه لا يريد التنازل عنه.",
        "growth": "توضح أين توجد قوة خام تحتاج إلى وعي، حتى لا تتحول إلى تمرد أو غضب صامت أو شعور بالرفض."
    },
}


def important_point_sign_house_text(name: str, sign: str, house: int, term: str, retro: str) -> str:
    sign_trait = SIGN_SIMPLE_TRAITS.get(sign, "")
    house_meaning = HOUSE_MEANINGS.get(house, "")
    meaning = IMPORTANT_POINT_MEANINGS.get(name, {
        "core": "هذه نقطة مساعدة في قراءة الخريطة وتحتاج إلى ربطها بالبرج والبيت والاتصالات.",
        "growth": "تُقرأ بوصفها مؤشرًا إضافيًا لا يحل محل الكواكب الأساسية."
    })

    motion_note = ""
    if retro == "متراجع":
        motion_note = " وكونها متراجعة يجعل معناها أكثر داخلية أو مرتبطًا بالمراجعة والتأمل قبل التعبير الخارجي."

    return (
        f"{name}: تقع في {sign} في البيت {house} ضمن حد {term}. "
        f"{meaning['core']} وجودها في {sign} يعطيها نبرة: {sign_trait} "
        f"أما وجودها في البيت {house} فيربطها بموضوع: {house_meaning} "
        f"والحد يضيف طبقة مهمة؛ {TERM_INTERPRETATION.get(term, '')}{motion_note} "
        f"{meaning['growth']}"
    )


def generate_asteroids_points_analysis(rows: List[Dict[str, object]]) -> List[str]:
    """
    تحليل مختصر للكويكبات والنقاط المهمة بعد حساب مواقعها.
    """
    if not rows:
        return ["لم تظهر الكويكبات أو النقاط المهمة في هذه النسخة من الحساب، وقد يكون السبب أن مكتبة Swiss Ephemeris على الجهاز لا تدعم بعضها."]

    priority = {
        "كايرون": 1,
        "الرأس الشمالي": 2,
        "الذنب الجنوبي": 3,
        "جونو": 4,
        "فيستا": 5,
        "بالاس": 6,
        "فولو": 7,
        "سيريس": 8,
        "ليليث": 9,
    }

    sorted_rows = sorted(rows, key=lambda r: priority.get(str(r.get("name", "")), 99))
    output = []
    unavailable = []

    for r in sorted_rows:
        try:
            if not bool(r.get("available", True)):
                unavailable.append(str(r.get("name", "")))
                continue

            output.append(
                important_point_sign_house_text(
                    str(r["name"]),
                    str(r["sign"]),
                    int(r["house"]),
                    str(r["term"]),
                    str(r["retro"]),
                )
            )
        except Exception:
            continue

    if unavailable:
        output.append(
            "ملاحظة فنية: حاول التطبيق حساب جميع الكويكبات المهمة، وحاول تحميل ملف الكويكبات تلقائيًا عند الحاجة. "
            "لكن بعض النقاط لم تُحسب في هذه البيئة، وهي: "
            + "، ".join([x for x in unavailable if x])
            + ". الحل العملي: تأكد من وجود اتصال إنترنت عند أول تشغيل، أو ضع ملف seas_18.se1 داخل مجلد sweph بجانب ملف التطبيق أو داخل Download/sweph."
        )

    return output

def dignity_status_for_table(key: str, sign: str) -> str:
    """
    حالة دستورية مختصرة للجدول.
    """
    if key not in PLANET_CONSTITUTION:
        return "-"
    return str(planet_sign_dignity(key, sign).get("status", "-"))


def format_lon_table(lon: float) -> Dict[str, object]:
    sign, degree = sign_from_lon(lon)
    return {
        "sign": sign,
        "degree": format_degree(degree),
        "term": get_ptolemy_term(sign, degree),
    }


def planet_positions_table(positions: Dict[str, BodyPosition]) -> List[Dict[str, object]]:
    """
    جدول الكواكب الأساسية.
    """
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    rows = []
    for key in order:
        p = positions[key]
        rows.append({
            "name": p.name_ar,
            "sign": p.sign,
            "degree": format_degree(p.degree),
            "house": p.house,
            "term": p.term,
            "retro": "متراجع" if p.retrograde else "مباشر",
            "dignity": dignity_status_for_table(key, p.sign),
        })
    return rows


def calculate_additional_points(jd_ut: float, cusps: List[float]) -> List[Dict[str, object]]:
    """
    حساب الكويكبات والنقاط المهمة.
    إذا لم يكن ملف الكويكبات موجودًا، يحاول التطبيق تحميله تلقائيًا ثم يعيد الحساب.
    """
    rows = []

    asteroid_file_ready = ensure_asteroid_ephemeris_ready()

    for item in ADDITIONAL_POINTS:
        # دعم الصيغة القديمة والجديدة احتياطًا
        if len(item) == 4:
            key, ar_name, swe_ref, needs_asteroid_file = item
        else:
            key, ar_name, swe_ref = item
            needs_asteroid_file = False

        try:
            if swe_ref == "CALCULATED_SOUTH_NODE":
                node_obj = getattr(swe, "MEAN_NODE", None)
                if node_obj is None:
                    raise RuntimeError("MEAN_NODE غير مدعوم")
                result = swe.calc_ut(jd_ut, node_obj, swe.FLG_SWIEPH | swe.FLG_SPEED)
                lon = normalize_deg(float(result[0][0]) + 180)
                speed = float(result[0][3]) if len(result[0]) > 3 else -1.0
                retro = speed < 0
            else:
                attr_name = swe_ref.split(".")[-1]
                obj = getattr(swe, attr_name, None)
                if obj is None:
                    raise RuntimeError(f"{attr_name} غير مدعوم في pyswisseph")

                # نحاول الحساب بعد ضبط المسار
                setup_swiss_ephemeris_path()
                result = swe.calc_ut(jd_ut, obj, swe.FLG_SWIEPH | swe.FLG_SPEED)
                lon = normalize_deg(float(result[0][0]))
                speed = float(result[0][3]) if len(result[0]) > 3 else 0.0
                retro = speed < 0

            loc = format_lon_table(lon)
            house = house_from_cusps(lon, cusps)
            rows.append({
                "name": ar_name,
                "sign": loc["sign"],
                "degree": loc["degree"],
                "house": house,
                "term": loc["term"],
                "retro": "متراجع" if retro else "مباشر",
                "available": True,
                "note": "",
            })

        except Exception as e:
            # بدل أن يختفي الكويكب، نظهره مع سبب مختصر
            if needs_asteroid_file:
                if asteroid_file_ready:
                    note = "تعذر حسابه رغم وجود ملف الكويكبات"
                else:
                    note = "تعذر تحميل ملف الكويكبات تلقائيًا؛ يحتاج اتصال إنترنت أو وضع seas_18.se1 داخل مجلد sweph"
            else:
                note = "غير محسوب في هذه البيئة"

            rows.append({
                "name": ar_name,
                "sign": "—",
                "degree": "—",
                "house": "—",
                "term": "—",
                "retro": note,
                "available": False,
                "note": str(e),
            })

    return rows



def generate_welcome_message(name: str, gender: str, positions, angles) -> Dict[str, str]:
    """
    بطاقة ترحيب قصيرة في بداية التقرير.
    """
    sun_sign = positions["Sun"].sign
    moon_sign = positions["Moon"].sign
    asc_sign, _ = sign_from_lon(angles["ASC"])

    sun_trait = SIGN_SIMPLE_TRAITS.get(sun_sign, "")
    moon_trait = SIGN_SIMPLE_TRAITS.get(moon_sign, "")
    asc_trait = SIGN_SIMPLE_TRAITS.get(asc_sign, "")

    name_clean = name.strip() if name else "صاحب الخريطة"

    line1 = f"أهلًا {name_clean}"
    line2 = f"شمسك في {sun_sign}، قمرك في {moon_sign}، وطالعك {asc_sign}."

    if gender == "أنثى":
        line3 = (
            "هذه الثلاثية هي مفتاح القراءة الأول: الشمس توضّح هويتكِ وإرادتكِ، "
            "والقمر يصف عالمكِ الداخلي واحتياجكِ النفسي، والطالع يبيّن طريقتكِ في الظهور والتعامل مع الحياة."
        )
        line4 = (
            f"بصورة مختصرة، يجمع هذا المزيج بين {sun_trait} "
            f"وبين نفس داخلية تحمل نبرة {moon_trait} "
            f"وطريقة ظهور تميل إلى {asc_trait}"
        )
    else:
        line3 = (
            "هذه الثلاثية هي مفتاح القراءة الأول: الشمس توضّح هويتك وإرادتك، "
            "والقمر يصف عالمك الداخلي واحتياجك النفسي، والطالع يبيّن طريقتك في الظهور والتعامل مع الحياة."
        )
        line4 = (
            f"بصورة مختصرة، يجمع هذا المزيج بين {sun_trait} "
            f"وبين نفس داخلية تحمل نبرة {moon_trait} "
            f"وطريقة ظهور تميل إلى {asc_trait}"
        )

    return {
        "line1": line1,
        "line2": line2,
        "line3": line3,
        "line4": line4,
    }




# ============================================================
# تقرير V6.0 المبسط التفاعلي
# ============================================================

MODALITIES = {
    "الحمل": "مبادر", "السرطان": "مبادر", "الميزان": "مبادر", "الجدي": "مبادر",
    "الثور": "ثابت", "الأسد": "ثابت", "العقرب": "ثابت", "الدلو": "ثابت",
    "الجوزاء": "متغير", "العذراء": "متغير", "القوس": "متغير", "الحوت": "متغير",
}

def analyze_modalities(positions: Dict[str, BodyPosition]) -> Dict[str, int]:
    weights = {
        "Sun": 3, "Moon": 3, "Mercury": 2, "Venus": 2,
        "Mars": 2, "Jupiter": 1, "Saturn": 1
    }
    scores = {"مبادر": 0, "ثابت": 0, "متغير": 0}
    for key, weight in weights.items():
        sign = positions[key].sign
        scores[MODALITIES[sign]] += weight
    return scores

def strongest_modality(scores: Dict[str, int]) -> str:
    return max(scores, key=lambda k: scores[k])

def planet_power_rows(positions: Dict[str, BodyPosition], aspects) -> List[Dict[str, object]]:
    """
    ترتيب تقريبي لقوة تأثير الكواكب على الشخصية، بصيغة مئوية سهلة للقارئ.
    ليست درجة مطلقة، بل مؤشر يساعد على فهم الكواكب الأبرز.
    """
    rows = []
    personal_bonus = {"Sun": 14, "Moon": 14, "Mercury": 10, "Venus": 10, "Mars": 10}
    angular_bonus = {1: 16, 4: 14, 7: 14, 10: 16}
    aspect_counts = {}
    for a, b, asp, orb in aspects:
        aspect_counts[a] = aspect_counts.get(a, 0) + 1
        aspect_counts[b] = aspect_counts.get(b, 0) + 1

    for key in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]:
        p = positions[key]
        info = planet_constitution_analysis(key, p)
        raw = 50 + int(info["score"])
        raw += personal_bonus.get(key, 4)
        raw += angular_bonus.get(p.house, 0)
        raw += min(12, aspect_counts.get(p.name_ar, 0) * 3)
        percent = max(5, min(100, raw))
        rows.append({
            "name": p.name_ar,
            "percent": percent,
            "level": info["level"],
            "reason": f"{p.name_ar} في {p.sign} والبيت {p.house}، وتأثيره العام: {info['level']}."
        })
    rows.sort(key=lambda r: int(r["percent"]), reverse=True)
    return rows

def aspect_badge(asp: str) -> Dict[str, str]:
    if asp in ["تربيع", "مقابلة"]:
        return {"symbol": "🔴", "label": "ضاغطة", "class": "hard"}
    if asp in ["تثليث", "تسديس"]:
        return {"symbol": "🟢", "label": "داعمة", "class": "soft"}
    return {"symbol": "🟡", "label": "مركّزة", "class": "focus"}

def generate_important_aspects_cards(aspects) -> List[Dict[str, object]]:
    if not aspects:
        return [{"symbol": "—", "label": "لا توجد", "title": "لا توجد زوايا رئيسية واضحة", "text": "لا توجد اتصالات رئيسية ضمن الأورب المعتمد في هذه النسخة.", "class": "neutral"}]

    rows = []
    for a, b, asp, orb in aspects:
        rows.append((aspect_priority_score(a, b, asp, float(orb)), a, b, asp, float(orb)))
    rows.sort(key=lambda x: x[0], reverse=True)

    cards = []
    for score, a, b, asp, orb in rows[:12]:
        badge = aspect_badge(asp)
        pair_meaning = PLANET_PAIR_MEANINGS.get(pair_key(a, b), "هذا الاتصال يربط دلالتين مهمتين في الخريطة ويظهر أثره حسب طبيعة الكوكبين.")
        cards.append({
            "symbol": badge["symbol"],
            "label": badge["label"],
            "class": badge["class"],
            "title": f"{a} {asp} {b}",
            "orb": f"{orb:.2f}°",
            "text": pair_meaning,
        })
    return cards

def generate_fingerprint(positions, angles, element_scores, aspects, chart_pattern) -> List[str]:
    modality_scores = analyze_modalities(positions)
    dominant_element = strongest_element(element_scores)
    dominant_modality = strongest_modality(modality_scores)
    powers = planet_power_rows(positions, aspects)
    strongest = powers[:3]
    weakest = powers[-3:]
    asc_sign = str(angles["ASC_sign"])

    items = [
        f"العنصر الغالب: {dominant_element}. هذا يوضح المزاج العام للطاقة في الخريطة.",
        f"الطبيعة الغالبة: {dominant_modality}. هذا يوضح طريقة الحركة: هل تبدأ، تثبت، أم تتكيف.",
        f"نوع الخريطة: {chart_pattern.get('ar_name', '')}. {chart_pattern.get('text', '')}",
        "أقوى الكواكب تأثيرًا: " + "، ".join([f"{r['name']} ({r['percent']}%)" for r in strongest]) + ".",
        "الكواكب الأكثر حاجة إلى وعي: " + "، ".join([f"{r['name']} ({r['level']})" for r in weakest]) + ".",
        f"الطالع في {asc_sign}، وحاكمه {SIGN_RULERS.get(asc_sign, '')}. هذا يحدد مفتاح الظهور وطريقة الدخول إلى الحياة.",
    ]
    return items

def generate_quick_summary(strengths, notes, creativity, challenges, summary) -> List[str]:
    """
    خلاصة قصيرة جدًا؛ لا تستبدل التفاصيل، بل تمنح القارئ نتيجة مباشرة.
    """
    items = []
    for source in [strengths, notes, creativity, challenges]:
        for x in source[:2]:
            if x and x not in items:
                items.append(x)
            if len(items) >= 8:
                break
        if len(items) >= 8:
            break
    if len(items) < 5:
        items.append(summary)
    return items[:8]


def build_report(name: str, gender: str, positions, cusps, angles, jd_ut: float = None) -> Dict[str, object]:
    element_scores = analyze_elements(positions)
    aspects = detect_major_aspects(positions)
    planets_table = planet_positions_table(positions)
    asteroids_table = calculate_additional_points(jd_ut, cusps) if jd_ut is not None else []
    asteroids_points_analysis = generate_asteroids_points_analysis(asteroids_table)
    welcome_message = generate_welcome_message(name, gender, positions, angles)

    general_analysis = generate_general_analysis(name, positions, angles, element_scores)
    chart_pattern = detect_chart_pattern(positions)
    core_analysis = generate_asc_sun_moon_analysis(positions, angles)
    planetary_analysis = generate_planetary_analysis(positions, aspects)
    houses_analysis = generate_houses_analysis(cusps, positions)
    dignity_summary = generate_dignity_summary(positions)
    aspects_analysis = generate_aspects_analysis(aspects)
    important_aspects_cards = generate_important_aspects_cards(aspects)
    midpoints_analysis = generate_midpoints_analysis(positions, cusps, angles)
    supporting_techniques = generate_supporting_techniques(positions, cusps, angles, aspects, element_scores)

    strengths = generate_strengths(positions, angles, element_scores, aspects)
    notes = generate_growth_notes(positions, element_scores, aspects)
    creativity = generate_creativity(positions, angles, element_scores)
    challenges = generate_challenges(positions, aspects)
    planet_powers = planet_power_rows(positions, aspects)
    fingerprint = generate_fingerprint(positions, angles, element_scores, aspects, chart_pattern)

    sun = positions["Sun"]
    moon = positions["Moon"]
    asc_sign = str(angles["ASC_sign"])
    asc_degree = float(angles["ASC_degree"])
    mc_sign = str(angles["MC_sign"])
    mc_degree = float(angles["MC_degree"])

    intro = (
        f"هذه قراءة شخصية أولية للخريطة الخاصة بـ {name}. "
        "تعتمد هذه النسخة على الخريطة الأصلية: الطالع، الشمس، القمر، الكواكب، البيوت، الاتصالات الأساسية، وحدود بطليموس بصورة مبسطة. "
        "الهدف هو تقديم قراءة مفهومة تساعد على معرفة طبيعة الشخصية، مكامن القوة، مناطق النمو، مجالات الإبداع، والتحديات التي تحتاج إلى وعي."
    )

    summary = (
        "الخلاصة: الخريطة لا تختصر الإنسان في حكم واحد، بل تكشف طريقة عمل طاقته. "
        "عند فهم الطالع والشمس والقمر، ثم ربط الكواكب بالبيوت، تظهر الصورة أوضح: أين توجد القوة، أين يظهر الضغط، وأين يمكن أن يتحول التحدي إلى نضج. "
        "أفضل استخدام لهذه القراءة هو تحويلها إلى وعي عملي: تقوية الصفات الإيجابية، تهذيب الصفات المتعبة، اختيار البيئة المناسبة للإبداع، ومراقبة التحديات قبل أن تتحول إلى عوائق."
    )

    technical = {
        "asc": f"{asc_sign} {format_degree(asc_degree)}",
        "mc": f"{mc_sign} {format_degree(mc_degree)}",
        "sun": f"{sun.sign} {format_degree(sun.degree)} - البيت {sun.house} - حد {sun.term}",
        "moon": f"{moon.sign} {format_degree(moon.degree)} - البيت {moon.house} - حد {moon.term}",
        "elements": element_scores,
        "aspects": aspects[:12],
    }

    # توجيه الخطاب حسب الجنس المختار.
    intro = personalize_text(intro, gender)
    general_analysis = personalize_text(general_analysis, gender)
    chart_pattern["text"] = personalize_text(str(chart_pattern["text"]), gender)
    core_analysis = {k: personalize_text(v, gender) for k, v in core_analysis.items()}
    planetary_analysis = personalize_list(planetary_analysis, gender)
    asteroids_points_analysis = personalize_list(asteroids_points_analysis, gender)
    houses_analysis = personalize_list(houses_analysis, gender)
    dignity_summary = personalize_list(dignity_summary, gender)
    aspects_analysis = personalize_list(aspects_analysis, gender)
    important_aspects_cards = [
        {**card, "text": personalize_text(str(card.get("text", "")), gender)}
        for card in important_aspects_cards
    ]
    midpoints_analysis = [
        {
            "title": group["title"],
            "items": personalize_list(group["items"], gender)
        }
        for group in midpoints_analysis
    ]
    supporting_techniques = personalize_list(supporting_techniques, gender)
    strengths = personalize_list(strengths, gender)
    notes = personalize_list(notes, gender)
    creativity = personalize_list(creativity, gender)
    challenges = personalize_list(challenges, gender)
    fingerprint = personalize_list(fingerprint, gender)
    summary = personalize_text(summary, gender)
    quick_summary = generate_quick_summary(strengths, notes, creativity, challenges, summary)

    return {
        "welcome_message": welcome_message,
        "intro": intro,
        "general_analysis": general_analysis,
        "planets_table": planets_table,
        "asteroids_table": asteroids_table,
        "chart_pattern": chart_pattern,
        "core_analysis": core_analysis,
        "planetary_analysis": planetary_analysis,
        "asteroids_points_analysis": asteroids_points_analysis,
        "houses_analysis": houses_analysis,
        "dignity_summary": dignity_summary,
        "planet_powers": planet_powers,
        "aspects_analysis": aspects_analysis,
        "important_aspects_cards": important_aspects_cards,
        "fingerprint": fingerprint,
        "quick_summary": quick_summary,
        "midpoints_analysis": midpoints_analysis,
        "supporting_techniques": supporting_techniques,
        "strengths": strengths,
        "notes": notes,
        "creativity": creativity,
        "challenges": challenges,
        "summary": summary,
        "technical": technical,
    }


# ============================================================
# الواجهة
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Tahoma, Arial, sans-serif;
            background: #f4f1ea;
            margin: 0;
            padding: 0;
            color: #2d2926;
            line-height: 1.9;
        }
        .container {
            max-width: 1050px;
            margin: 0 auto;
            padding: 18px;
        }
        .card {
            background: #fffdf8;
            border: 1px solid #ded4c4;
            border-radius: 16px;
            padding: 18px;
            margin-bottom: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        h1, h2, h3 {
            margin-top: 0;
            color: #3b2f2f;
        }
        h1 {
            text-align: center;
            font-size: 26px;
        }
        h2 {
            border-right: 5px solid #9b7b4f;
            padding-right: 10px;
            font-size: 21px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, select {
            width: 100%;
            box-sizing: border-box;
            padding: 10px;
            border-radius: 10px;
            border: 1px solid #c8bda9;
            background: #fff;
            font-size: 16px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }
        .grid2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        .buttons {
            display: flex;
            gap: 8px;
            margin-top: 14px;
        }
        .copy-report-btn {
            background: #3f5f45;
            color: #fff;
            width: 100%;
            margin: 8px 0 16px 0;
        }
        button, .clear-btn {
            border: none;
            border-radius: 12px;
            padding: 12px 18px;
            font-size: 16px;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
        }
        button {
            background: #6f4e37;
            color: white;
            flex: 1;
        }
        .clear-btn {
            background: #d8c7ad;
            color: #2d2926;
            flex: 1;
        }
        .section {
            background: #fff;
            border-radius: 14px;
            padding: 14px;
            border: 1px solid #e6dccb;
            margin: 12px 0;
        }
        .item {
            margin-bottom: 10px;
            padding: 10px;
            background: #faf6ef;
            border-radius: 10px;
        }
        .warning {
            background: #fff3cd;
            border: 1px solid #f0d98c;
            border-radius: 12px;
            padding: 12px;
        }
        .technical {
            font-size: 14px;
            background: #f7f7f7;
            border-radius: 10px;
            padding: 12px;
            overflow-x: auto;
        }
        .muted {
            color: #6d6259;
            font-size: 14px;
        }
        .hidden {
            display: none;
        }
        @media (max-width: 800px) {
            .grid, .grid2 {
                grid-template-columns: 1fr;
            }
            h1 {
                font-size: 22px;
            }
        }
        .platform-nav {
            display: flex;
            gap: 8px;
            justify-content: center;
            flex-wrap: wrap;
            margin: 10px 0 16px;
        }
        .platform-nav a {
            background: #fffdf8;
            border: 1px solid #ded4c4;
            color: #5a3f2a;
            text-decoration: none;
            padding: 8px 12px;
            border-radius: 999px;
            font-weight: bold;
        }
        @media print {
            .form-card, .buttons {
                display: none;
            }
            body {
                background: white;
            }
            .card {
                box-shadow: none;
                border: 1px solid #ddd;
            }
        }
    
        .app-subtitle {
            text-align: center;
            margin: -6px 0 4px 0;
            color: #6b5a46;
            font-size: 16px;
            line-height: 1.8;
            font-weight: 600;
        }
        .app-author {
            text-align: center;
            margin: 0 0 18px 0;
            color: #4b3828;
            font-size: 15px;
            line-height: 1.8;
            font-weight: 700;
        }


      .report-watermark {
        position: relative;
        overflow: hidden;
      }

      .report-watermark::before {
        content: "جميع الحقوق محفوظة للمطور astrologer.ab@";
        position: absolute;
        top: 8%;
        right: -10%;
        width: 120%;
        height: 120%;
        transform: rotate(-24deg);
        font-size: 28px;
        line-height: 3.2;
        color: rgba(80, 55, 35, 0.075);
        white-space: pre-wrap;
        pointer-events: none;
        z-index: 0;
        text-align: center;
      }

      .report-watermark > * {
        position: relative;
        z-index: 1;
      }

      .rights-footer {
        text-align: center;
        margin: 18px 0 8px 0;
        padding: 10px;
        font-size: 14px;
        color: #5f4936;
        font-weight: 700;
        border-top: 1px solid rgba(95, 73, 54, 0.18);
      }


      .rights-footer {
        display: flex !important;
        align-items: center;
        justify-content: center;
        gap: 8px;
        flex-wrap: wrap;
        direction: rtl;
      }

      .developer-avatar {
        width: 42px;
        height: 42px;
        border-radius: 50%;
        object-fit: cover;
        border: 1.5px solid rgba(161, 128, 81, 0.95);
        box-shadow: none;
        background: transparent;
        vertical-align: middle;
        pointer-events: none;
      }

      .rights-text {
        display: inline-block;
        line-height: 1.8;
      }


      .quick-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }
      .quick-box {
        background: #faf6ef;
        border: 1px solid #eadfce;
        border-radius: 12px;
        padding: 11px;
        line-height: 1.8;
      }
      .aspect-card {
        background: #faf6ef;
        border-radius: 12px;
        border: 1px solid #eadfce;
        padding: 12px;
        margin: 9px 0;
      }
      .aspect-head {
        display: flex;
        gap: 8px;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        font-weight: bold;
      }
      .aspect-label {
        font-size: 13px;
        padding: 2px 8px;
        border-radius: 999px;
        background: #efe5d6;
      }
      .power-row {
        margin: 10px 0;
      }
      .power-top {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        font-weight: bold;
      }
      .power-bar {
        height: 9px;
        border-radius: 99px;
        background: #eadfce;
        overflow: hidden;
        margin-top: 5px;
      }
      .power-fill {
        height: 100%;
        background: #8b6f47;
        border-radius: 99px;
      }
      details.accordion {
        background: #fff;
        border: 1px solid #e6dccb;
        border-radius: 14px;
        margin: 12px 0;
        overflow: hidden;
      }
      details.accordion summary {
        cursor: pointer;
        padding: 14px;
        font-weight: bold;
        color: #3b2f2f;
        background: #fbf6ef;
        list-style: none;
      }
      details.accordion summary::-webkit-details-marker {
        display: none;
      }
      details.accordion summary:before {
        content: "▶ ";
        color: #8b6f47;
      }
      details.accordion[open] summary:before {
        content: "▼ ";
      }
      .accordion-content {
        padding: 12px 14px 14px;
      }
      @media (max-width: 700px) {
        .quick-grid {
          grid-template-columns: 1fr;
        }
      }

</style>

    <script>
        async function loadCitiesForCountry() {
            const countrySelect = document.getElementById("country_code");
            const citySelect = document.getElementById("city_select");
            const manualBox = document.getElementById("manual_city_box");
            const manualInput = document.getElementById("city_manual");
            const selectedCountry = countrySelect.value;

            citySelect.innerHTML = "";
            const loadingOption = document.createElement("option");
            loadingOption.value = "";
            loadingOption.textContent = "جاري تحميل المدن...";
            citySelect.appendChild(loadingOption);

            try {
                const response = await fetch("/api/cities?country_code=" + encodeURIComponent(selectedCountry));
                const data = await response.json();

                citySelect.innerHTML = "";

                data.cities.forEach(function(cityName) {
                    const option = document.createElement("option");
                    option.value = cityName;
                    option.textContent = cityName;
                    citySelect.appendChild(option);
                });

                const other = document.createElement("option");
                other.value = "__manual__";
                other.textContent = "مدينة أخرى / أكتبها يدويًا";
                citySelect.appendChild(other);

                const currentCity = citySelect.getAttribute("data-selected");
                if (currentCity) {
                    let found = false;
                    for (let i = 0; i < citySelect.options.length; i++) {
                        if (citySelect.options[i].value === currentCity) {
                            citySelect.value = currentCity;
                            found = true;
                            break;
                        }
                    }
                    if (!found) {
                        citySelect.value = "__manual__";
                        manualBox.classList.remove("hidden");
                        manualInput.value = currentCity;
                    }
                }

                toggleManualCity();
            } catch (e) {
                // إذا تعذر الجلب، نبقي القائمة الموجودة أصلًا من السيرفر ولا نحذفها.
                let hasOther = false;
                for (let i = 0; i < citySelect.options.length; i++) {
                    if (citySelect.options[i].value === "__manual__") {
                        hasOther = true;
                        break;
                    }
                }
                if (!hasOther) {
                    const other = document.createElement("option");
                    other.value = "__manual__";
                    other.textContent = "مدينة أخرى / أكتبها يدويًا";
                    citySelect.appendChild(other);
                }
                toggleManualCity();
            }
        }

        function toggleManualCity() {
            const citySelect = document.getElementById("city_select");
            const manualBox = document.getElementById("manual_city_box");
            const manualInput = document.getElementById("city_manual");

            if (citySelect.value === "__manual__") {
                manualBox.classList.remove("hidden");
                manualInput.required = true;
            } else {
                manualBox.classList.add("hidden");
                manualInput.required = false;
                manualInput.value = "";
            }
        }

        document.addEventListener("DOMContentLoaded", function() {
            const countrySelect = document.getElementById("country_code");
            const citySelect = document.getElementById("city_select");

            if (countrySelect && citySelect) {
                loadCitiesForCountry();
                countrySelect.addEventListener("change", function() {
                    citySelect.setAttribute("data-selected", "");
                    document.getElementById("city_manual").value = "";
                    loadCitiesForCountry();
                });
                citySelect.addEventListener("change", toggleManualCity);
            }
        });
    </script>


    <script>
        function copyReportText() {
            const reportBox = document.getElementById("report_copy_area");
            if (!reportBox) return;

            const text = reportBox.innerText || reportBox.textContent || "";

            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(function() {
                    alert("تم نسخ التقرير");
                }).catch(function() {
                    fallbackCopyText(text);
                });
            } else {
                fallbackCopyText(text);
            }
        }

        function fallbackCopyText(text) {
            const temp = document.createElement("textarea");
            temp.value = text;
            temp.style.position = "fixed";
            temp.style.left = "-9999px";
            temp.style.top = "-9999px";
            document.body.appendChild(temp);
            temp.focus();
            temp.select();
            try {
                document.execCommand("copy");
                alert("تم نسخ التقرير");
            } catch (e) {
                alert("لم يتم النسخ تلقائيًا. ظلّل التقرير وانسخه يدويًا.");
            }
            document.body.removeChild(temp);
        }
    </script>

    {% if not report and not error %}
    <script>
        window.addEventListener("pageshow", function() {
            const fieldsToClear = ["name", "year", "month", "day", "hour", "minute", "city_manual"];
            fieldsToClear.forEach(function(fieldName) {
                const el = document.querySelector('[name="' + fieldName + '"]');
                if (el) { el.value = ""; }
            });

            const gender = document.querySelector('[name="gender"]');
            if (gender) { gender.value = ""; }

            const country = document.getElementById("country_code");
            if (country) { country.value = ""; }

            const city = document.getElementById("city_select");
            if (city) {
                city.innerHTML = '<option value="" selected disabled>اختر المدينة</option><option value="__manual__">مدينة أخرى / أكتبها يدويًا</option>';
                city.setAttribute("data-selected", "");
            }

            const manualBox = document.getElementById("manual_city_box");
            if (manualBox) { manualBox.classList.add("hidden"); }
        });
    </script>
    {% endif %}


    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-2XZSMG55TG"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-2XZSMG55TG');
    </script>


    <style>
      body, body * {
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
        user-select: none !important;
        -webkit-touch-callout: none !important;
      }

      input, textarea, select, option, button {
        -webkit-user-select: auto !important;
        -moz-user-select: auto !important;
        -ms-user-select: auto !important;
        user-select: auto !important;
        -webkit-touch-callout: default !important;
      }

      .no-copy-note {
        font-size: 13px;
        opacity: 0.75;
        margin-top: 8px;
      }
    </style>

    <script>
      (function () {
        function blockEvent(e) {
          e.preventDefault();
          e.stopPropagation();
          return false;
        }

        document.addEventListener('contextmenu', blockEvent, true);
        document.addEventListener('copy', blockEvent, true);
        document.addEventListener('cut', blockEvent, true);

        document.addEventListener('paste', function(e) {
          const tag = (e.target && e.target.tagName || '').toLowerCase();
          if (!['input', 'textarea', 'select'].includes(tag)) {
            return blockEvent(e);
          }
        }, true);

        document.addEventListener('selectstart', function(e) {
          const tag = (e.target && e.target.tagName || '').toLowerCase();
          if (!['input', 'textarea', 'select', 'option'].includes(tag)) {
            return blockEvent(e);
          }
        }, true);

        document.addEventListener('dragstart', blockEvent, true);

        document.addEventListener('keydown', function(e) {
          const key = (e.key || '').toLowerCase();
          const ctrl = e.ctrlKey || e.metaKey;

          if (ctrl && ['a', 'c', 'x', 's', 'u', 'p'].includes(key)) {
            return blockEvent(e);
          }

          if (key === 'printscreen') {
            return blockEvent(e);
          }

          if (key === 'f12') {
            return blockEvent(e);
          }

          if (ctrl && e.shiftKey && ['i', 'j', 'c'].includes(key)) {
            return blockEvent(e);
          }
        }, true);
      })();
    </script>

</head>
<body>
<div class="container">
    <h1>{{ title }}</h1>
    <div class="platform-nav"><a href="/">الرئيسية</a><a href="/profile">بياناتي الفلكية</a><a href="/natal">قراءة الخريطة</a></div>
        <div class="app-subtitle">تحليل شامل للهوية، الطالع، الكواكب، البيوت، الكويكبات ونقاط النمو الذاتي</div>
        <div class="app-author">من إعداد الخبير الفلكي عباس الشباني</div>

    <div class="card form-card{% if report %} hidden{% endif %}">
        <h2>بيانات الميلاد</h2>

        {% if not swisseph_available %}
        <div class="warning">
            مكتبة Swiss Ephemeris غير مثبتة. ثبّت المتطلبات:
            <br><b>pip install flask pyswisseph geonamescache</b>
        </div>
        {% endif %}

        {% if not geonames_available %}
        <div class="warning">
            مكتبة المدن العالمية غير مثبتة. ثبّت:
            <br><b>pip install geonamescache</b>
        </div>
        {% endif %}

        <form method="post" action="/natal" autocomplete="off">
            <div class="grid2">
                <div>
                    <label>الاسم</label>
                    <input name="name" value="{{ form.name }}" required autocomplete="new-password" autocorrect="off" autocapitalize="off" spellcheck="false">
                </div>
                <div>
                    <label>الجنس</label>
                    <select name="gender" autocomplete="new-password" required>
                        <option value="" {% if not form.gender %}selected{% endif %} disabled>اختر الجنس</option>
                        <option value="ذكر" {% if form.gender == "ذكر" %}selected{% endif %}>ذكر</option>
                        <option value="أنثى" {% if form.gender == "أنثى" %}selected{% endif %}>أنثى</option>
                    </select>
                </div>
            </div>

            <div class="grid">
                <div>
                    <label>سنة الميلاد</label>
                    <input type="number" name="year" value="{{ form.year }}" required autocomplete="new-password">
                </div>
                <div>
                    <label>شهر الميلاد</label>
                    <input type="number" name="month" value="{{ form.month }}" min="1" max="12" required autocomplete="new-password">
                </div>
                <div>
                    <label>يوم الميلاد</label>
                    <input type="number" name="day" value="{{ form.day }}" min="1" max="31" required autocomplete="new-password">
                </div>
            </div>

            <div class="grid2">
                <div>
                    <label>ساعة الميلاد</label>
                    <input type="number" name="hour" value="{{ form.hour }}" min="0" max="23" required autocomplete="new-password">
                    <p class="muted">الساعة بنظام 24 ساعة: 13 تعني 1 ظهرًا، و01 تعني 1 بعد منتصف الليل.</p>
                </div>
                <div>
                    <label>دقيقة الميلاد</label>
                    <input type="number" name="minute" value="{{ form.minute }}" min="0" max="59" required autocomplete="new-password">
                </div>
            </div>

            <div class="grid2">
                <div>
                    <label>فرق التوقيت عند الولادة GMT</label>
                    <select name="timezone_offset" required>
                        <option value="" disabled {% if not form.timezone_offset %}selected{% endif %}>اختر فرق التوقيت</option>
                        {% for tz in timezone_options %}
                            <option value="{{ tz.value }}" {% if form.timezone_offset == tz.value %}selected{% endif %}>{{ tz.label }}</option>
                        {% endfor %}
                    </select>
                    <p class="muted">مثال: العراق والسعودية GMT +3.</p>
                </div>
            </div>

            <div class="grid">
                <div>
                    <label>الدولة</label>
                    <select id="country_code" name="country_code" autocomplete="new-password" required>
                        <option value="" {% if not form.country_code %}selected{% endif %} disabled>اختر الدولة</option>
                        {% for c in countries %}
                            <option value="{{ c.code }}" {% if form.country_code == c.code %}selected{% endif %}>{{ c.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label>المدينة</label>
                    <select id="city_select" name="city_select" data-selected="{{ form.city }}" autocomplete="new-password" required>
                        <option value="" {% if not form.city %}selected{% endif %} disabled>اختر المدينة</option>
                        {% for city_name in city_suggestions %}
                            <option value="{{ city_name }}" {% if form.city == city_name %}selected{% endif %}>{{ city_name }}</option>
                        {% endfor %}
                        <option value="__manual__">مدينة أخرى / أكتبها يدويًا</option>
                    </select>
                    <div id="manual_city_box" class="hidden" style="margin-top: 8px;">
                        <input id="city_manual" name="city_manual" value="{{ form.city_manual }}" placeholder="اكتب اسم المدينة هنا" autocomplete="new-password" autocorrect="off" autocapitalize="off" spellcheck="false">
                    </div>

                </div>
                <div>
                    <label>نظام البيوت</label>
                    <select name="house_system">
                        <option value="P" {% if form.house_system == "P" or not form.house_system %}selected{% endif %}>Placidus</option>
                        <option value="W" {% if form.house_system == "W" %}selected{% endif %}>Whole Sign</option>
                    </select>
                </div>
            </div>



            <div class="buttons">
                <button type="submit">استخراج التقرير</button>
                <a class="clear-btn" href="/clear-profile">مسح البيانات</a>
            </div>
        </form>
    </div>

    {% if error %}
    <div class="card warning">
        {{ error }}
    </div>
    {% endif %}

    
{% if report %}
    <div class="card">
        <h2>التقرير الشخصي</h2>

        <div id="report_copy_area" class="report-watermark">

            <div class="section">
                <h3>{{ report.welcome_message.line1 }}</h3>
                <p><strong>{{ report.welcome_message.line2 }}</strong></p>
                <p>{{ report.welcome_message.line3 }}</p>
                <p>{{ report.welcome_message.line4 }}</p>
            </div>

            <div class="section">
                <h3>بيانات الخريطة الفلكية</h3>
                <h4>مواقع الكواكب الأساسية</h4>
                <div class="data-table-wrap">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>الكوكب</th>
                                <th>البرج</th>
                                <th>الدرجة</th>
                                <th>البيت</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for row in report.planets_table %}
                            <tr>
                                <td>{{ row.name }}</td>
                                <td>{{ row.sign }}</td>
                                <td>{{ row.degree }}</td>
                                <td>{{ row.house }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                {% if report.asteroids_table %}
                <h4>مواقع الكويكبات والنقاط المهمة</h4>
                <div class="data-table-wrap">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>النقطة</th>
                                <th>البرج</th>
                                <th>الدرجة</th>
                                <th>البيت</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for row in report.asteroids_table %}
                            <tr>
                                <td>{{ row.name }}</td>
                                <td>{{ row.sign }}</td>
                                <td>{{ row.degree }}</td>
                                <td>{{ row.house }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}
            </div>

            <div class="section">
                <h3>أهم الزوايا المؤثرة</h3>
                {% for item in report.important_aspects_cards %}
                    <div class="aspect-card">
                        <div class="aspect-head">
                            <span>{{ item.symbol }} {{ item.title }}</span>
                            <span class="aspect-label">{{ item.label }} — الفارق {{ item.orb }}</span>
                        </div>
                        <div>{{ item.text }}</div>
                    </div>
                {% endfor %}
            </div>

            <div class="section">
                <h3>البصمة الفلكية</h3>
                <div class="quick-grid">
                    {% for item in report.fingerprint %}
                        <div class="quick-box">{{ item }}</div>
                    {% endfor %}
                </div>

                <h4>ترتيب الكواكب حسب التأثير</h4>
                {% for row in report.planet_powers %}
                    <div class="power-row">
                        <div class="power-top">
                            <span>{{ loop.index }}. {{ row.name }}</span>
                            <span>{{ row.percent }}%</span>
                        </div>
                        <div class="power-bar"><div class="power-fill" style="width: {{ row.percent }}%;"></div></div>
                    </div>
                {% endfor %}
            </div>

            <div class="section">
                <h3>الخلاصة السريعة</h3>
                <div class="quick-grid">
                    {% for item in report.quick_summary %}
                        <div class="quick-box">{{ item }}</div>
                    {% endfor %}
                </div>
            </div>

            <details class="accordion">
                <summary>تحليل الكواكب واحدًا تلو الآخر (10 كواكب)</summary>
                <div class="accordion-content">
                    {% for item in report.planetary_analysis %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                </div>
            </details>

            <details class="accordion">
                <summary>تحليل الكويكبات والنقاط المهمة ({{ report.asteroids_points_analysis|length }} عناصر)</summary>
                <div class="accordion-content">
                    {% for item in report.asteroids_points_analysis %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                </div>
            </details>

            <details class="accordion">
                <summary>تحليل الشخصية والطالع والشمس والقمر</summary>
                <div class="accordion-content">
                    <div class="item">{{ report.general_analysis }}</div>
                    <div class="item">{{ report.core_analysis.asc }}</div>
                    <div class="item">{{ report.core_analysis.sun }}</div>
                    <div class="item">{{ report.core_analysis.moon }}</div>
                    <div class="item">{{ report.chart_pattern["text"] }}</div>
                </div>
            </details>

            <details class="accordion">
                <summary>الجانب العاطفي</summary>
                <div class="accordion-content">
                    {% for group in report.midpoints_analysis %}
                        {% if group["title"] == "عاطفيًا" %}
                            {% for item in group["items"] %}
                                <div class="item">{{ item }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endfor %}
                </div>
            </details>

            <details class="accordion">
                <summary>الجانب المهني والمالي</summary>
                <div class="accordion-content">
                    {% for group in report.midpoints_analysis %}
                        {% if group["title"] == "مهنيًا" or group["title"] == "ماليًا" %}
                            <h4>{{ group["title"] }}</h4>
                            {% for item in group["items"] %}
                                <div class="item">{{ item }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endfor %}
                </div>
            </details>

            <details class="accordion">
                <summary>الجانب النفسي والزوايا العميقة</summary>
                <div class="accordion-content">
                    {% for item in report.aspects_analysis %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                    {% for item in report.dignity_summary %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                </div>
            </details>

            <details class="accordion">
                <summary>المواهب والقدرات</summary>
                <div class="accordion-content">
                    {% for item in report.creativity %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                    {% for item in report.strengths %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                </div>
            </details>

            <details class="accordion">
                <summary>التحديات والدروس</summary>
                <div class="accordion-content">
                    {% for item in report.notes %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                    {% for item in report.challenges %}
                        <div class="item">{{ item }}</div>
                    {% endfor %}
                    <div class="item">{{ report.summary }}</div>
                </div>
            </details>

        </div>
    </div>
{% endif %}
</div>
<div class="no-copy-note" style="text-align:center;">حقوق القراءة محفوظة. النسخ اليدوي غير متاح داخل الموقع.</div>
<div class="rights-footer"><img class="developer-avatar" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAA33klEQVR42u29eZBt13Xe99vDOecOPQ/v9RuBhxkgQIIDRIKkSTMRFdqRREuW40hJKSU5dhyVKrItV1RKSlGkPxK7PJRKCWPFdpIqSZYtKQ5FDRQHcRJFiSBAENPDe3gz3jz0dOcz7CF/7HPOPbffg8wBHDI0qgtodPfte9bee61vfetbawvvPd/pH6+eO+vxHi8gaXWIk4Q4bpEkCQiBcxbnHM6CsRZnLc571lYXxXf6s+nvtDc0Hmc+L3KybILJc6wtAF/+I8GDB7z3OOdQSiGlQusIEFgH1hq8d4wnxuPBOkNRpIyGA44cOSL+/wXYa/RJ5pM4wlqHh2BhF06mEBInXDC/lCAA71Fa0WrF5HlBfzDg5o0b3Lh2jUG/R55nFFmOVJIoTojjmKQVs7yySjoZ+iLPkMBDjz7+bV8M8e1yQbu9oQeHEJIoioljjbWWonAUeUaWjTGFwTuDdRYRViO4oDim1+tx4dwZzp05zY0bNzh3+hS97R2EkEgpMcZgrAEECHDGkrRbbBzY4PG3vJlHHn0UrTRRnLC8tsFddx0V/59YgFu3dnwURYALb0BK4jgmijTGWIyxFHlKmk6wxuJcgXcOAcgoYjQcceL4cb7y5ac5ffIk6WRCluZ470jiiCjSSCHQUUQrSfDek+Y5eW7I8owsy/E4Dh46xFve+laeePKdrKxtEEURkW5x5OgB8f/KBbh5c9N7PEoqtK48n0CqsABaC6xxFMZS5BlpOi4XwIBz5FnKiRMneebpL3Hq5EkmwyFpmrK4uMh8O6EdS5wpyLMcqQTtJMF5cM4zyTJGkxyPxzjBJC8YDgfEccIb3vQmvvcHfpD7HngYrSK8D3Hl0KFvzUJ80xfg6tXrXkqJEOF5pJSEExA+lFIkSYJSUBSOvCiwpiDLU0y5W72zfOqTn+APf/8P2NrcxFkHzrK+1OGeg+scXFuincRIKRiNUowxJHHEzZ0+/VGKEILt/oA8K0BKBmmGE5rMWAb9IfsObPB9P/hDfPAHfgjnXPj9pIXSEasrC+L/kQtw/twp75yg1e6ilEIIedsCCCHKBYgRgnL3G4zJyfMM5wzOFnzqE5/kdz/yEa5evITJc9ZWFrn/8BqPP3gXS3NtWq0EKSXeOYo8ZzgcY60lzXKGwwmbvTGpceRphvGenfGE0SQjt56k1WJrd0CcJPx7H/hLfM9f+j6OHj2KVBqtIrTWRLGi006+KQvxTUFBly9d8M45QJa+Xs5833uPEIIS5yDw5QIJvHc4Z8P3veOjv/d7fPZzn2dnZwcpJSuL8zzxyDHe8fhDLHRitNY4axECvPPgDHNJTH80ppNoupEiVoKdYcpYBjCrFAhnKZxHSM/aQgevEz76Ox/mpRee5z/9sb/BO9/1XsIz+BqpfTMWQb/+xn/VO+dKI/vSqB6wpRuaLkZ4Go8XArwPn3i890gleO6pZ/nsZ/6YwXDA7vY2iRR81xMP897vepS1lUWUCPax1iBceC1nMrSASCvG45SW0kRKIrynpSG3jjhSSA9OQlp4jC2Y5Ib5TpvLF17lX3zolymygve9/wMzm2Y4mvi5blt8Ry7A1auXvfe+tGO1c0S1geqHmP63QwgFZWyov+WDaxoNh3z6U3+EsQXDfh+c5a2PPshfeNujHFhfRWuFFOBMgZMR3nu8tVgniSNdI6w8leAdi3MdIiWZFAUqN8j5Nk6AFRrrPUVRgN9mlHm2bm3yO//2N7n/oYe57977cc7UMazXG3pjclZXV16XhZCvx4vcuHGjtmx4nwIx3d97fjq4n/J5Gj8XPq1z6Ejz8svHOXniFfq9PpEQPP7gvbzvHY9x9NB+Wp0OSRwjpUJJiRIgvEPiUUqjlCKKFHGk0UqilaTbiljodljudljqtFmaa9NOIuYSxVK3xfLiPEf3r7FvLiZNU06+fJyPffR3sc7V72+6Q+DKlcv+O2IBtrd3QvLqgxvx4f3Vn3eI+40/7as8CQiQUUWa0WDAZz/zGaIkIdGawwf28cQbH+S+Y3fTaneI4hghBFJKVBSjlA5ZcgVtpURJhcAjpUAqTRRpWklEp5Uw322x0Gkx32nRSSKSSNGONfvXl3nknsN0IsH2To/f/8iHefGFrxAnLay15SYpY5VznDn9iv+2LkB/MPKV9YQQUO1sAV4wY9wQE2qPU7soKcpTULourTUvH3+Z61evcuzYMfbvW2ff0hwP3HOYpZVltFJIIZFKIZXGC1kvBlIivAMh8UIgRG0upNQoFRFFUUj8Yk0n1rRiRSyhrSUL3S7719d57J4jLM61efX8ef7Fr3yIyWRMFEVliPJU8MF7x4njz/lvywJM0twzs8v9nl0uXmP3z8aFYB5fIyNrDDs7Wzz40MOsLC+yPD/HA/fcxcGDBwKcVTosttKoSKOkwnqPEAolNUIqvAMhNJFuIZVGqgB3tVKliwpuKVKKWCuSRBNFEoWj3Wlx9OA6h1YXmZub5wt//Bl+6R//w+BKhQ95SbV9hMA7z0vPPe2/pQswHE18FVB9I7h6P/X4dUDe8/0QFdye00CdI+RZhrWeu++5h439G9x19DD33Xs3nXYHISOEihE6Jko6yKiDanWJki4yipFRghcKUAipQSikjtG6FQyvNVIHrkgrTRxHREqhpUQpiRIeLSCOY1YXOigBcdzit37j1/n85z5Ht93GWYsv4al3vn7ml55/xn9LFmC3P/AzaGavi6mN72toI2qkM4U6vjw/ISCXWbIQjEZj8jwjGw9ZX13lvnvuZnlpIby2CgaNOgvo7grR3CrJ3CrJ3DJCxjgEQifIKEJ4AUIiVISKYqI4IYqTOrmK44Q4iknihDiKUEoilUB4RyuOWFvosNAO6Cq3ho/9we9jrCufQZQxy9YxRwjB819+6mtehK8Jhvb6Q1+hlsrJyAas3OttfHDsteFFveVFAw2JErp6nPdEUcTS0gpLSwu0JPjhFt25LkIUIT+IW6hWFxm1QgrnHSCIihybZQgdYVWEUAabpghvkTLCawnOI51HeoeU4K1ESIlwCkyBKTdBFGsWum2Wu222hxkLCws888xTXLl8hZWVZYoiB09I1MoF8TicdXzl2af9m9/yhHjdT0C/PwgORfgZ2NhENaJOuhoRwE9dz3QRphtlBpIKgbWWbreNlpK5ToeV1TWU0ggVIaRGRQk66aB1gijpBxm3EFGCbnVwTiB1hIpbSB2HE6Fb6KSLjkNMUDJCSY2OYiKtUUKgymQNPFpKWnHEXLtVu6ubN2/wleeeJWm1y53vZ12oB0ok9tKLz/vX/wQIUTl0hBQzrqcEkfgyAw7VqpAJTw+smPmsuKEqJpdYFmsKVlaWmfR20aqNEgq8RUVdojhGJR2Ujsu/47BFii+KEBviDnY0RjkQKkJGbSgsEoW1DrxAqhgtFMI5rDMI7xEy5BBC+joWqUjTbcckWjFJU7xzXLxwASnFHbGFKCGf982T/jqdgOFo4mfwjvczGKf28XvMvTcRm+70OuWdCSTWOZx3CO/ptlskkcKZFIC43SVqz6GUgtLdeWvw3mPyDIEMATJYAO881jiQEVInSJ0gdIxXCrTGxzFIhUcEZCU1UZSgIw0ItI5YmGuhlQIESuu6aDSTuRNcpytjXmWL4y+94F+XBRiNU+/rF581uqCJZCp4Wf7snrSrDsy4GjkIMYWr3vuwANaiBSwtr6CVRDiH1BqpA6Pq8VhbYG0e3EB1/oqsqlYCEmcdpihwttoCHmeKkrDzwV1WLrxcNKUitFR4b9FK0Wm1abcT4jhhbm6Bffv2N9xs+Rp1ahbimRRT73DyxHH/DS3AcDj206Webt9qlWsEI+qzNxMduO0rGiekeo1pkMZ7hLfEkabV6QTDS4HCl+7NgQNb5Ng0BamRcQcZt/FldiqECPUCIbHW4KzBG4P3gQzUQiKcD/8fjxQCh0cqVe9s6z0oSRzFtOKIdithYWGRfRsH8N7WG0iKkHHWIMI5HA7hg2GFEFy8eNF//TGgYWhfMpviDg5QNGNE9d+1eymR0Gy0mi5oU+VgCrw1aKWxpqAYjxDeoYTEFRYhDN45lJTh+3mO9R6TZSA0yBgVd/AeTGGwRZCreK2RSqEjgTcF2AJbhL/l61zG1UkhFZ0iodVq4dCsr69z+NBhiqIk5kqZTIUAnXN450NMwVF9844x46tZgGayVe96P0utVW/8TkUdgcDV+cDexLiJiMojLRVOKpxzCGcZ9Xu4yZCO1iGgW4ObFLQXlnn1/HleeeUUc+0Oc/NztLRmrtMh0hqvE0yW47zAe4EzBTqOUVIipMZ7KKyFPAsur3JhxuGRQZlR1qCtFywtryKygrd919vZt38/WZpO84DaPg2XImR4OjEN6Ds7Pb+8fGeN0p97AqqAVvl0f/sPBC6/PgCNfV47ZP9atbiZkza5epabF89iOyuI0s/HpkAoTW4dihyb5zz3wgk+9kef4dUrNziwsZ+11RX2rSxxcH2VxXabdpzgi5zW3BxRu42QAhW18M4EqKxDJo1O8EiMyShMeJ/WFljnwq4Vgtw65hcXaUvFG9/4JnQUkaYpojK+K+OiF9MYV+U1eCIhkUJ97SdgPEn38Dx3NqMHhJ+NCb6BBKb0hK+D1F7XJbQkv3WDq1/4OD6K2BGbLBw+Rjro0ekqEBJT5AivOXHiBCfPXWNuYYWl4YTTr17k+VdOs9DtoJxjuZ3w+EP3c2T/PvbtW0dYg9YRSkWkeYZzOV5qisKRGnAiIjMF1oBU4cQ6F9geh0DFbRLdRXnP8uoaztoGrvMzz1exRFU8kEKAmNpia2vHr64ui69qAfydj8P0yFUBs3b3U8wjhKyz4urNVco2MQuj6iAuvOXa8y9w+B1Psm9xgWGRk8SKditBSIXygnG/T393wMMPPczC4iKvvPAsp199lVNnLtAbDBhmKdotcvnaNUw6QgtLW0vi9jxSa9Jhj9x7nIwZjcZk1tIfjdjZ2UUp6MSKhW6CFz7okbzAle4kjiIWF5ZCLlH5gtIdN/DDzPPKKucR4rVteqcFGE8yj58Sa6IJO5vwscHvzMYAN0s7lJSQmMHOIQxLKcA5dHeetaN3Ib1F+wxXRKwsdokVELcQMufq1hYLCwssdwRbV89TjHa5d2Mf++c63Lh6ORTinUXkE5xpkacjdKsFeUaxdZPeYIdr2wM2eyO2hyNGuWFrdxdjQlAdj8c88Yb7eOjYATwC5wXjyYShM9z/8MOsrK6GWnUz+fSBVHQlhJ5x3RU3JqdgZHNz26+tzVbS9O2739+BZGtA0L0BVzANtHj83hLkTBCu/GQjUDuHiNss3XU3SktMlNBJuiRSBP2QlDjn6HRajPu3+O1f+whnb/QYWbi1vUO7FXP3yiIbi/PESuLylHvvOcz+/ftJRxnpaMKwv8313R6nL91iZzxmVDjOXb5Kah1Jq4UzQUv6xZdO0e20WV7o4DwUFnJrOHToKO12m/F4PLPhfDMTKXOLKrT58jtipvrx78gDxpOJx09ftvqc8jvidhQ0A+9v53nCO2qwiM34UB8SQTS3gNASn6fI8S7CpmWsdnhvmZubJx+NefDRN/Ld73kP73/3k8wlio21ZY7ddy/DwYhuK8EJWD54lPsee5xuNyGd9MlMzs3tHXZ727SVZyWRvOW+o7zr0Qd55OhB7tpY58DqCtv9IeeuXMcLgfMW50FHEfs3NgJ1UjO+Zf2iFB6IsiiELBdgJncStfG992xu7fjXPgE+4FePrI/WrLHL4LKHcg6+XOLZ4yP3kHAVXU2Diq6+jBaXGJy5zKVXz3PwsceJ9RzFZEgyvxySpSLlnjc8zmMLy2xv7fDK03/GD73nXeTGIPG0D24wv9hmaaXD4nybONbML8wz10koTM5wNKGVJLSShJ3dAe25eVZXlpEupxOtMTGOM1c74cR56ixZC4m3IZ9AiLA1y9jg6rjnax6oOgJCyJmkdcoIy9eOAd75kH00SWM/5WzEa0XsmiPfg368b5TxZqGtL6mM6sCopMXw1i0GOyMQGmGDLtQKyPMck40h7jAe9hF2zPrGKq1OxG5/yGi3T6znWFxd5L77j3FwbYViPEQ6RxzF5HmOlrC2OE+vN2L98BG++MLL3HruON12wr7FOR44tJ+7D67Tm2RYY4mVZG5+Huc8X/r93+YNjz1Od34ea0xNBDZkBgjfyPHFtDZ9G5rcQ9vXCzAajco1CkIqvwfx8Bq+zHuHv80h7amMNcnr8hTIBnXknEdGEUrHLK7vZ25xnnwyQkYJ1liEkMRxi+HOFkQxeE+73cLmOXlmUIuwvLbC3ceOsrK0iO7Mk08mZOMhxuQ4D4vzCe3uAq04Qccxb3/4fk6eO899Dz3E2bPnefr4Kd76hvtZ27dOrCVSSLqdFoyHLMwt0ep2G0ScZxaoBAiLCPSEqGn72d1fkZjNYKxv1+yI2318IyPei46mO93P7vq936/jgtwjR3Hhj+gY3WmjJilYEyhv7/DWkCysEre6uDRn2NslKwrSyYQiTVlcmGftwXtZXd+g3W7jncFZSzEekk8m5GkGAhbn5kBFxMsdTF5w1/oy+7sJo0nKY4f3sbnYxjnHYkujpUDoFtIYtPf8Bz/y48RJQjoazcLoJvNbAQs5Y7g7VsX9a7kgUfq4mRpvo8Ai7uB+vN9b8xUzecL0NcTsuywfwHmBkAJrLHMHD6BXVijyAhnrsBAmR0QJMm7TWlyjGI9DQhRHLK0eZm5+DhXFxO05vJIU6YhiNCYbDTHG4X0QALeSNsJD1GrhOh28zeiomHYMRghWV+cxJmc+jtB4rJSYdMKjb3s7Rx96mNFwOGUFKtKxLsG6KUvmy80lp8/75yWqGuDG9eu+OzdXu3LR2PmipBuc9zXD1yCRp6CmwvoNhxR+p7GAYlYzUf0NTyg1SqXpriyEBo10gtYaZQzkGVIY4vYcc6v7iYc9EAIZaWyek02GREmHzuoG1hS4wZDJaEyWW4SK0SpHKoXysNBJSLMCJ2OUAKUkWWFJjWVxcYFOkmBKXWosHA898SS25IaEENiKPfJixum6OvmaQmzRIOKEEKXWNBji1q0tv76+KvQeprl87SnxdqfqTtMt+SYhJUSNLf0e/acQYs8Rmn7hrEUkbVQU4wGlY4wrQgOeB+kFKmkjUYi5xcA+5hnFJCebjNm6eol1FLo1j4q7tJY3GOz263ijdIxuS2SRE0tN3NX0B0OUBKE03kFU0tGFMdDqUhjD/Pw86wcOYYuiLn9S5i7eB4M7PJSVcl+Ci4qar4r1t5VpG3aVt7PPjqbG03k3/eU9wdj5Kffh6wL17YWYGv8344zYQ3vICKRC+FCNUnECOq7frFQaGbfqwk+RWyajMdtXLjOcFCTtDun2DTyS9vohotYcOm6BlKGEaQXFpEArTbczx0K3Q0srWlFEW0W0dUQSxQilQWqMMRy+7yG6C4slB7QXyUyfOTBHIhT4Z81cgxT/Ghta7tmnAVKJGp7UFvJ7qOiZxaj1PrMkFY30HH+HXLDKlJ0PpcK4HXaQC8jHuVIx5xxCaZyxZMMhRZozGY4Z3rpJv9dn9dBRlg/fRbS4hkoSXFGgOgvEi2sIoXBeoKUCR5Ay6ogkbtGO20GSIsPB9QiQCpTCOs+BY/cjpZqNhXtwvZ+mNag6GfC1y6pc9m0huXkCbhPKVoFVUL9Y099Vx6r5M9PgNEUGXgic81MX9Jq0t8MrhYnbOJMHFlHKOsYIa7GTCfl4iLOGIssY93cZT0aIVof24iIyiog6XfJBj61LpxnsbpH2hxTWYb2jkySoKGI8nACKSEfESRLkjVJjQssg3gvSLCfuLnDXg2/AFPls9t/QO3lZWs0LJMH9OMFM3WSvC2oGZAB96eIF3+50ZxomKlO7PUjmtqyuWRdokHH14jhf5nWikRU2EEHztQG5sIYb7oYFEaBkkK/bIsfbPsVoTD4e09veYjzskzuPSlrk4xFPffQjvHziLPc88jAPPnw/WzdvMOr3yQnJZRwpoiTBFhkmTdE6RkcemefoKCiqDR7jIU1TDj/0IEur6xR5Vj/3tAAj631XkYy+0jg5PxP/hFANDkyUgoFgo63tXa+998jyQfF7drjzZSSfancqQ7om1BWzcsSq3iLuiF/Lxdjr1nxQvlGpmoXEO4srDFiBcWPS4YDB7jbjYeB3VLfN/qP3kCRttnd6jNKCP/nis4zynOHONsPhiP5ohPKeQ/tXS+2owKQZqhuF5y6PtkOQG4sFsixjdd8BtI4o8rRx4qe6JlHCaF/REPhZphQ/Y5cm/S7LhZBCoENfbfjC7cH0odwoEeLPIbRv0+VOExQ3oxiQddWsPm1NJOWnSZorK0rOuhLxeFxhSUcD+r1tev0e8dIidz38OForjDEsHzrCA4Xj2rVrXLxwkZ3ekK3dHsPhkIU4QlrP4Y1VfCwprEEVBYiQ8KEkOIcTHuvD313d2CgByLQcW0lQquze1ehuqgwXVSz0fpb38ZVbnVbFAXQl7fbTX20Y3882WDSqD01f2KwN4KcuSHhu637Z2xNQnQJfugqUDqqFIDugmGSYNMdZQW/rBteuXSVe3WD/fY9ihWI8GNDr97l86RJZltOKFYI5nIgYFwVCSQ6srLC8OAd40nSM1w4VKYQAW1hs+fecC+1KcbvL2v4DOGvqXeuQSOGoiRcPsqLgy4rfzG70ewJ2FQsa5V0BaClF6aemLOZMN8seP+8b/3aNiN9kPusy3azlmebDTV84hapCKhAK7w3WFiH4eodT4GzB1vYtxijWDh3h3JlTJK2EPE05f+oMuXd02y36/QGDcRbGEyjJyFuubG8yP9dCGo10BiNHwc0pRWELChsyXyEkxhQcuO8YK+sbOFP2tXnqjVWrPKpSq5+ioEpZgSghaVMR0WhMDCcjjF/Q4QfljAtxJf3ahFozEpU97MZtqgg/6wtds1rk/B37BkS1j6IIX0xKiYeDcn6EUCEL1Z0W1y+fZ3dnh/mFRZyxeC1JpKY/GnL5xk0yG4zRVoo8z7mxswPecWh9jVYckXiLdZYkiUMdWEVlvJM471g/eJg4aZGnY6SQdUfA1H2WMWCG/xczWD+4dlW7LNGQ6dT9ENKjZbnyTX7fO4ur5iy8Rn242dUYpNpumqAwzR+cmyXnuEM9oUr6PGAQUOQlX+RxUiC8RGnN3NoqO9dvcu70ZbZ2h7TbCQfXV+kminySooqcGEeOpDCGQnhGkwlKKa7v7tKfjFnsdNhYWca6nBUBQmuMtzgUxoOQio0jx2YTSOdqhGitrQNxQG/ijuFQCoESCllW9GjQ+lPvIpFSqFkVw52k5g2oOGX/pm9ib114NoveI2ls8EkzXErZ7OCkwjpHlmcURYHScaASkg4r+/bhrQEHG/v2kUjNtQtX2b2+y/b1Hi71HFpcZjmSLGhNR4AShFkRpiBzjp3JhJ1JSuY8xlsKZ7A2DATJTEFnfpEDd92NNUWpfPO18X0jvlXP6VyzHBueVUpJaEaegqFaV+UbtLyQwQWxR8fv/e2sHXukJtyBMfVe1IipemN7a8hNWW9AELJR/AGZdCkI7KhUgkiCI/SCmaLA24I3PvYw9z9wP8Y4rl24xOblW4xHGc47er0+shghC48BhPFQFOhEMxlPkJ0OkzxHRV1UpEhNaG31WlDkBXc9dIyFxRWcMSilZuNYqYALTXq+hNriNnGalJLKs1SQ1c+cgKnL0lKpWZ/daJa+TfYlZsuIIPaEWM8UF8xKFKuFUmLPofXTpC+JI7ZvTsj6A9qJJjMOby1eRuAsO1ubqLjN/Q/cT0sLiqjN3Y88yr59t5js9snHOZcvXUFJhfOO3dEALwVKCKK2YpAVZGlKZ32ZteUlinzMKC9rvzJCKMm9j74ZqSTWuylyqXMjbjvxtTSWJilQFujlrCK8WRuuM2FZ/lQDDIYZDc7VJTXvG3LyhlquWXKsoGuFfSuhLE0+pArkUk4XrTxNUay5fmOT3/7IZ/jgW49QZFkocguPo8AZg7WWQ4ePEOvQDSlsTmoycuEZmgm93jZOOjrzMSbLWdVdlle6ZH4N6x3GWayHjbVVokgxnjiKwqEizSSfsLz/EHfd/zBFnjcmutxeTpxxt1X5Ucw2H4aCUgPA+KbEJ+Re4QQ0XVAFL93eE7CnJNloyqgWzdeJh5xFT81cQVBLGZu41DlLp9Pm//zwJzh46BCHjh7h8pmT6FaClFBkY9LJmIWlReJWh2w8CPDPQZFn9LZ3uXTxOlev3wQhyHJDEkW0WhqUIPKShTjg+Elh6bQ0QkmsihHaIyLNeDjkXW99J535BUyez7C/otGM6P3t6m9CWyBWNCQ3lVT9TrrZOkFzyGo3+oZOpHnEKoS6l5DyTTJ1j8GF29sTVtETlXq4hgo45+l02zz/4it84U+/zPvf/15yJymKHGsM1jtsFkbQtDpdlNJYF9CLI/QTRFph8gwtJK0oDo0d3pIZS24MkYRYCaQPQdkUGWkeBLwISW84Yu3gER5963dRpGmZmDbVe/J2nasgEG9VDlCN5GmM5qmbEJutWKXSvEr8dHjxhizLT3F7k4QTe7pjqurXbcV7KWfleA0FtPeifjgBWGNpJTGnz17gf/pnv8axY0e579ghLucDrAvBbTzOSIcjxlmOF5K57iI6bhFHClfsBqxdWDqtiLTVwhSGlo4Cq6wFUoGWodBiSqibFYYiNRRWUFhLWhje/YEP0up0KAqLmun6aRDt/g6cVx3ngvtVFagQzXasJgkQiAhfVtb0XLct6i4YRN3+w54OFva+qRoJTU9NUBXvbUkStX60qSM1xtBKWtzY3Oaf/W//mivXNvmeRx5CAPuP3cvlEy8y2r2MiCN2hhnD/i5OKRYWFtE6CprRpI0sPN3OEocOaGK9yWicYp1FSoeUDu8NTghyY8CGhpA0z0kLiKKIwXjIG9/xXu5/5DGK3CDULCxnj0S/2pxVtU00T0mjZTXogpovIWolUWXEtbWyJFlTAULMZMAzrlqIGc7jtl7J8g3gqatostGMV1EXzoXq0fxch0tXN/kH/+hXuHz5OlE0HeoUxxF3P/4Ez37iMm1pEe0Fhre28TsjVpYL4tiQZRZrBFIlzC92UTLCGkunHVQQRZaRmzEIj3EOL3NGwwnGOYwNk1rGaUoyv8zb3/d+irwgipI9kpvZPKe2jd/LP8ppI4YUDQgqppkxYP20lamitiV7pIfhazubdFTptr+9f2C2UjRbiKjcj3NhCFOkFfPzcwgp+ZOnvsLP/cI/4eTJMygdGjMq3U1RFBy4+24efud3MxzldDptFpdXMUXOcJKSTcZkgy1G/W3ScQjQg0Gf0XhC4SzoEGTDiYS0yDAOUuvZ3B0wGKekhWGnP+C+Rx5jYXm1/tu3V/qmqsFmTiBu8++ixP9BUt8U5U7xRlOi76eqCN/A76HTcBa8VG078g6GbxSMa/hZPYxSinY7odVqkReOi5evc/3my3zuC1/mqaeeBQetdgtjLALF5tZ2nchYa7nn0cdI05Tjn/8E3fkFtPJMxn36ShF5z2Q4IMsKlNDsbu4wGI1DR3yW45zFC09uDGlmyZxjsz9gPM5QSuLGOVIqlg8eI1IKaxtKZsSeyl/DFt7W5FvzJFSxMjALfg9jwGw+sVcXJHwVUEVwH366qn4P8hF7ZYclwWZtkGpHWiNbCbmQDMYpJ85c5uKl6xw//goXLl4lLQxShCMqZOBsPKAjzasXL9MfjlmY62CtxVrDI297giLNOPHUp4k7C0wmQ6K4QHrY2hky7A2wxjHqD3GAUpNQXdPBEM47MmO5MRgEOYoXZGmOFJJ3fOAH+fxTz9OeX+Dd73wnaRYWRYg7acZFDYRCs6DfI2ErT4RkKtZtlGZFo5uoeco0wPx8V+z2Bh7KZrPa14vXVHh5V3YFOofWiiTpYJ3j1q1tXjl9gZeOn+Xlk2e4dWsbax2FyWm12mgdB3eDRZfZpXOeOIq5eWuTU6df5W1vfrgM6qHT8U3vfjeTNOXy8adQKqI/ymhFEiFhkhVs7gxCS6oHZx1SKZIkCmQejn6aMcoLvBfkecb80ioPvO19PPT4k3zpK/+SX/jFf8Cv/ur/waGNfYzGYyCaqeU2+TC/R2pTZchBJU09wKES5/pST+Uarso5x9raqrhNGeecnxlUN03fROlaXG2YdjshiSWj8YSr127y4vGTnDp9kQuvXuXGrS3S4YDJZIAHFpb3kbQ7oanauqlWtEz6wCGlIZ1M+MrzL/O2Nz88S1Q7xxve8R6uXTiP6V8jihOGwxQVtVFagM1rJtb68D5N5rACUucZjlNskSKk4N43PsmjT76f+eVVjCkYjsfcunmTn//5X+Cf/uN/yMLCPHmeN1gAP6sPdzYkqneQOE1zp+bCiDtomd2dpInNatZ011vrArWqFEkrQWnN9vYuJ06e4eUTp3jhxROcO3+JwWBEFCe02wnOGkbjAZNRD6ljujaIVQVh11aKed8Ya+adReB59ivHsT/6V6cTsITAes/cXMzbP/BBPvtvfx2d9omVIissIu5i3RZFYVBakiQx1sMkN4zzlOFogFCag8ce4rEnv5u7HnwjeE+WjfHOc+3qdea6c3zpqS/xkz/19/jFX/h53vDw/eS5IU3TGfc7ixBFo9ew6oFQe6T4vkZCM4pAfwdt6NLigri1ue1tWYyJY0UcRbQ6XYxx7PR6nHvpFM+9cJwvPvUMFy9cYjQeUxhDO07ozs/TbifkRc6g12MyHpJnGa2oQ55nJCJBqqr2XHYlOo/0FpzACtCR4vz5i1y9sc2RAys19y6FwBnDwcP7eM8P/DB/+L//L8R+RNxqobzHWrBOoFULryKydEKvv4NOOjzwpnfyyBPv4cCxh0iSBFNkmKKg3W5x4dwVNre2UAqSVosvf+lp/tZ//l/w13/4h/ne7/0A9959hOFoQlEUNa3gSo6r6pT0e5Efe6aHNYRcFcxutinNuKA40tBuU5iC0Sjl8tVbvHLmVU6ePMfps+e5du0Gw0EvsJqEilUShakjUmoKYxmPxmTpkCKbhJxPa7xzOO9RdQOfmM4GlaHaZYwB79na3uTEK69y5MDKLI0hJUVhOXT0AO//0Z/gmU/8AeNb5+m0Y44e2WBrewepI4x1yLl57nn8HTz4XX+R1f2HEVKQ5yneG3QUYYxBS825c+cYDkcsLy9QFDlxknDr5k1+6Z/+E37jN36D7//g9/Mj//F/xJHDB+n3euUoZXdb/SR40z2zj+rumD1c2p4ca2YBTp27yJnTZ3n5xGnOnL3IzVtb9HZ7WGtLl+DqFc1NgUcSqRipIxCS8WhEkWehi90UxEkbpSKcd0EkVysmqgDmkZQ8vwOlNaPRkNNnL/Ked76JJBIzx1VIQZoWHLnnAP77fpgvfuITtKRhY36RxasX2b5xiSMPvYnVw/cyv7aBkIKiyAPnonRZJAqnb5JNOHnyZB3fvHMYD1oq4pZme2uLX/6lX+bDH/4dfvzHfowf/CvfS7fbZjwehjpBRbghcITe4rohY2YcWC1YmZkedscFeOLNj4q//RP/tRdC1YxFpVLz3ofp5tYCNuQFSqOjBK0049GIPE9RUk5nhwoVaNnAPNUVIxqlB2NyTFHUsxpMUXD16nU2t4cc3lioT0pV9kySiN3dCZ/55/+G5z7/BZKlee46eozljQ1yt8H2QPCWBx5ke3uXPMtRWpcFJouzYUaEc57NrR0uX7kaiDxrywZEh3UWZySRlKyurHD9+nV+/r/7eX73Ix/hb/3NH+Mtjwe1XJ4VoGTZlCVmpn/tpXC88zUNs7SnY/420tsUBUqFlTLeNdvesS4o1iQK50BKjdaaNJuQTiYoKYlbbdJRD+8sUku0CrDTVWo3pXAQ+H2TT6lrR83B37p5nZubfQ7um2sY3xNHmus3dnj61z5D+8qAA1Gbsy8f5+pzzzK/uM7S0govXb/EK3/yZ/zwz/690vi+rHmHJDEvCowpuH5jk35/EHx5bSAZEi3nMISiTqvVIlIRzz33PD/90z/D93//9/Gf/Mhf5cD+NcbjMUVeIGTYaNUsbKlUAwm5O3cdvda0lOef+aQoiiLcxVLpc8S06K6kRkodmD8lw6j5yRhrcqSO0FFSr74tLHlhgkRDlHMUnCdLJ0zGQ0xhEIgwilJWEw01Ozs7bPcGDMc5Uoo617h85Qb//Gd+mfErN0k9dJf2cdfdj3Bw/yGKfIhylsfuf4TnP/Vpfv1Dv0K32y0zewveY6zBGkthHdu7PWyeN55tOuomxKjAIYXZEbYc2gG/9Vu/xd/5uz/Lb/7275HnhqXFBVQ1z6LE/rK8RGJmuIkQLC3Oi69qXI0sNS2irG1W2n8hFVpLtNboOA7F82wSplY5S1I2WVS+XuBJ4hjw9Ps7pKMB2SQYP1S4itCcoVQYmifCXTC93i6DYcZuf1JTGqNxzk//5M8xuHCLJErIrl3n1vXLpCZnbd9B7jt0jK3N67x05TxLBw/y0d/6TZ790tPErVZo8qs3lCcrLJO0mGL7Oh+pKK8ygDpRy2iMMXgvabW7XLlyhQ996H/l7//Mf8+//u3fZTJJWZifr90kjUy4ygWkkF/9vKDnn/m4qNLpahQLDbJJqFCgsEWONTnOFugoIU5aQeLnPV7IQAsrQZKEAXvD4W45JkxMJ9GWLKmQEqkkSil6u7sURcZglJdNE5Z/9a/+iPUj95PPddm3tsZDb3kry3MrbN+6xubWdebnl8jjiAtbV+lNxljv+djv/WFZ3XO1MQobjK+lalavZ2u9fqpwqHvjkOW4huB6pZacOvUK//OHfoW/+9M/y0c//mmSdpdut9tIMKf51OIddv+fO7DJ+zJgGVsnZkqqcmRYpeu3OFuAVOg4QappF4kUspzrYyjyjFaSBJGTNcStpN4VUpaLaS2FMWgdMxmP6fd65a0Xgo998llu7Yz5yx/8D0nuXuOLp46zcfd9PPmOJ1lbWqW3s8Wrl8+TShhmKUYp/sqP/wT7j9zPmZOn0XEU2oyEwFtBluUkWmBNNlPvDUqOIFH3DckNQpb5iyszYUduwoidVqvNxYsX+R//h3/Ez/3cL3L8xGmSdpv5+flyupd9bX3Vn7cALzz9MREU5j4wi7OtkVibY2xaDlCKZyCnAOKkRas9j7MGU17K452tU0Idx3WQdM4hvMDbMLg7y1Ju3LyJtY4/e+YMw7Hl6JEDZKMJb33fuziXbvHSnz3F3NIidx19gANLG5zYvMT1nW0OHHuA7/sbf5Mn/+K7OHL0EOfPXQ7jy5wvZ0A48BaBK4cvzVYE656EZguVc0glqi6OEn4GliArg3DcSvjUH32Kv/NTf5//5r/9BT77+T8lSRLmuh2Wl5fE1zczTpQVstKo1Zsx1mBMgXUW70UYjBqFsTDee4wzdBdWaXcXSthX+sWq28R5dGl839RZVhjVOwa72wwHOZcvbXPk8Drrqx36/QGdbod7/sJbeO7SaY7/6RfZvHmFdithmGVs3P8gP/STP8mDjz2EFpYjh/cTxQmbN3eQInA0aZ7TjqNwMouiLJE26r3i9kJMRcnUlARVT3AorxYmnN5Wp8tkMuaTH/84P/kTP8Xf/i//K/70qWe+/plxL335E6LZlFwxhGEYXgHOE0UJSatNnHRKqYVDSkU6GZYDvMMDKqnKtqPZBzPGlMUYg6kG8QnYunkL7wyLi20kjrWVRdZXF9jZ7nHo2DE6R/dz5tJ5Lt+8yPOXT7Nx1728/0f/Mw7ffZQ8neA9RJFg/8YaO9t9lFSM0wxXZCSxpigyXDlHLtQB5G2xoCqyhOu1AmISdbWrIUOUQdxsrMH6AKe9s3z205/ife99t/iGpiaeeOGzYtrhWFa3bB4YTBXmNWsdo3UUrhS0DqkismyMLUIiJMpkRJVVqmn1qOwZaJb8So5lNBwgvEGVs0cLa1hdXWBxrkOaZexbWuOtj7+DfQePMXGWeN8iy/vWGI0mWDy+HAa4tNgliiLG45TJaIQuO2+KLKsRjvCz2WtNG1tHngcgEEVxwPiNJovwHKrB/8tAeVsoTMGFC6f+nQNEv6q5ocef+7SQJWqwJsc7W+6QgN+jKC7ndNqyVUcidUJhinBMvQ0ByYWgJPxUQRzkf65mGquJh+NRH1U+qCTw/MZYVpbnUCKgmfb6Cr3hgM1Jj8GwRztSJV8zndcjFayszOGsIVEibAApyYtsqtvfq1utmy48kQ7QWErRECEEeU0Nt0Wzi8ghcJw/d+Krmt76VU/O9c7hZdDPO1sEzB7FRFFS+35P9dCKJO5Uw1dAhDmewnmEEvVM6WbPbTVpF+HRSjEajTDWonWQeEshMYVFKhnaSTsL9LducmXzMtYZ2q055ufnaCWaft9QmJxISrSURLFCAIXXFLlESRHoDxnQjb9DB3vV4SIajSsQ2imlELjyhHkxbZP0ZU+Y56uf4f1Vz45+8cufEM7ZoNUEhNQlFxTVlyd4UaYwMqTk1YxlreNS6j3VgQajm0Bv+EZznws9a6PxiMlkPCMD8c6S50UQWaU5l86exXtLO27TbXVwzhFFCa12G10Ka33J2spyekCkwiCONMtum21H0//XdWGJQE1nnJZgqNZK+VDnqGZnA1w4+9LrP7w7QNOPC+ftFBvXC1ByIWVokkLWDXfee3QUlbKY6c6wxpbznMvT1QjOUkpGwwHpZFLnCAgRKl3G4HcnjLcG7GQp964fYr7VrXewc5ZOO6mvMbTO1g0WQkyz+8lkcpuKY+aug0Yvm5BVI6NDiL26KTnVU3nB+TMvfk2X+3zN9wecOv5noppiXnE3rvTd1rgGlRF6cau2TaX0TD7iq86ZqtLtpg0fQkom6SSMCCshoCrdBd5T3BgwZz33HznCwvwSWikunjvLYLcXLmmQgjiJkGUHtveiVrFWQ2jT8aie87NXRlnJaJpQp4pZbuYOgap91eGF4PzZ57/mm5W+rhs0zpx4SoRxkIF8cqHFOagSZeB0pFTBAGXDQhzH5VwIN21ZqrpqyvHB9RhnKSmKgsGgP+1KkQKhJD437Lx6ne7SHIsb+xiOJvTyETu3rnHuxZdI2q0wcCmOaLdaJQhoFNR1yNbH41E9s8jvkY3UcNvkM2q2KU8k6zbVigW9cOb5r+taq6/7DpkXnv6YiONW6XocSona2JUuPlwzFW6601GEVnqql2/UnesSn7W1KzHW0u/3UFKVCgyPjBT9G7v4Xso9D99L2h9wY+saxjlaWnPyha/UtdtwEUOE1GVsKnsTIhnaWseTUUjC/J67DGS1aQK8NLaogUIVo8Jn1SED579O439DCwDwhU//G1H2kwZIWunghUZLhZLhJFR15iiOwwM6j7WmvI68OYG2nLlZTiYZDoZIFRrnwu16inRzwOH9ayRacfHsaTJbsBh36La6nDvxMsPdHkkrDPWIonA5T5Dei3qgRp7nZGladodODT9VuskZjF8LlIUIlETDZV04+/w3dKHbN3yP2Oc+/qtCK4k1eR0shaxk2mEilpQSk+flfV+ivh27yYbaigZwtlacDYb9ssI2nUvRSQWHNja4fOoc27vbtJKE1bllhFRs3rjG7q0bJEmrHEevqPKXqiCEFKRpuK9YSF8v7qz4bKrrlM0JKD4MiKgEuOe/QeO/LgsA8Mnf+5cizPS3DV2MbyRYIaOsum6mbii4BepRv6Ie8qqUZjgczjQ726xgZW4Om+ZsXb1Kp9vh0PohnNQUpsDlEy6eOouoE64y+COwZYHFexiPx6Rpdluj4ZR/nt7yJOr3VUYpEfzn2dNfeV2uMnzd7pL8zB/+qgB417//171vkHf1XH3nyPOMdquNM6FPV8jpDaplFhPUbC5c6DYc9memTLnMoL2gd+06kRIcvvtezl+7wmQ0ZJynREJy/eJFisKEmrWQaKWmpUbvAc1kEqQmQsm6WuZnOpZlfQlcKIVM3c6r5156XS/zlLzOH1/41G/WdxQLGaheZx1CSrI8DarlOklips9YlEGuam/t9/tYF264tnjcJKV/8SZGeFaPHWFhcYXN3U12Jj06cYu51jyb164yHIxKUlCgdCidCiqlmmQyGWO9DafDz870qca9STGdb1G9x9fb+N+UBQD40h9/ODySI9xUUc5c886TF0UQzipZU90NjNdQGkuGwyF5nqHLWRZbl64x2emxcvQgS+vrnDt9kt5wl1acsDq3RBTFXLt6iclojKk0PDJQI6Lh3gb9AVJFr9FwMq2T+QZB97Vkt9/2BQB46vMfFl/6wu8IV+10GS7CybMUiSzxuWt0jzTnLQdUMhqNSCdpeTckXDp1lqX1RVYOr3Hh1Bku37iEkpKNhTViFWNcuAZxPBpgTLjXS5a35FXjGJxzDEZjpIqnk77qBhVVmkTWVb8LZ14U3yzjf1MXoK4vP/0x8dKznxTVnSu29P+y9v+l4LXU5FBrkQSTyYThcIiKIrJJRt7rcfDeI2S7A66cPkukFQfWDhK15ijygnE+hsIyHg6xzlMYi0CE2zOqMZnOMho1cwBx2zR4ITznz7wozp9+QXyz7fNNX4Ca0v7yJ8XzT39cCCEoTFH732nttYKfARFpFZHnGcNhnySJGezuooFEay6/cBKpPEcO3sP6vkPk2YTeeJc4SkhQ9HZ2AoVhQh1Ya1UudqCx0zSrc42q90tJgZTw6tkXviWGf91R0FedQT/zcQHwjvf+oNeRxpgca32Z9IgSg4dM1JiCfn+XONak/T52d8StC1e5srvLvqN3MXCWi5cvMBzs4vEsdxYZTcb0dnbLm1ltPbi10hcVxjBJ02nd14FQkvNnvnVG/7YuQPXxxc/9X/UDP/Km9/kqE61voJAS5z27u7thYuIkZfv6DW4sb3L0vrsxRcb5069w4/olrC1Y7SwTJS12+rtMJiOU1hSTMGVXKln3O4csONw5du7Mc4Jv84fmO+Dj5ec/UxviLW//y75iRAG2traIk5jtWze4vnWdxY0l5lfnOfvSy1y/cRnhHQcW18niiCxP2R32yNMJrVaLbDymMI6k1BsJIfhrH3y3+GsffDffKR+a77CPZ5/66G278sXTW/7GxYu0kpiNe45w8/yrvPrqecZ2Qqe7gJ6bZ6u3RW/YwwmBcB6lJd/zvscE3+Ef/zcjFV3EZ8DnfAAAAABJRU5ErkJggg==" alt="المطور"><span class="rights-text">جميع الحقوق محفوظة للمطور astrologer.ab@</span></div>
</body>
</html>
"""



# ============================================================
# واجهات المنصة الأولى
# ============================================================

PLATFORM_AVATAR_B64 = "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"
PLATFORM_LOGO_B64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/4gIoSUNDX1BST0ZJTEUAAQEAAAIYAAAAAAIQAABtbnRyUkdCIFhZWiAAAAAAAAAAAAAAAABhY3NwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAA9tYAAQAAAADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAlkZXNjAAAA8AAAAHRyWFlaAAABZAAAABRnWFlaAAABeAAAABRiWFlaAAABjAAAABRyVFJDAAABoAAAAChnVFJDAAABoAAAAChiVFJDAAABoAAAACh3dHB0AAAByAAAABRjcHJ0AAAB3AAAADxtbHVjAAAAAAAAAAEAAAAMZW5VUwAAAFgAAAAcAHMAUgBHAEIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFhZWiAAAAAAAABvogAAOPUAAAOQWFlaIAAAAAAAAGKZAAC3hQAAGNpYWVogAAAAAAAAJKAAAA+EAAC2z3BhcmEAAAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAAAABYWVogAAAAAAAA9tYAAQAAAADTLW1sdWMAAAAAAAAAAQAAAAxlblVTAAAAIAAAABwARwBvAG8AZwBsAGUAIABJAG4AYwAuACAAMgAwADEANv/bAEMAAwICAwICAwMDAwQDAwQFCAUFBAQFCgcHBggMCgwMCwoLCw0OEhANDhEOCwsQFhARExQVFRUMDxcYFhQYEhQVFP/bAEMBAwQEBQQFCQUFCRQNCw0UFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFP/AABEIBgAF6gMBIgACEQEDEQH/xAAdAAEAAQQDAQAAAAAAAAAAAAAAAQIGBwgDBAUJ/8QASxAAAgEDAwMCBAEHBwoGAgIDAAECAwQRBQYHEiExCEETUWFxIhQVMnKBscEjQlJikZKhFhckJSYzNDU20RhDU3OC4URUg2OT8PH/xAAbAQEAAgMBAQAAAAAAAAAAAAAAAQIDBAUGB//EACoRAQACAgMAAgICAwEBAQEBAQABAgMRBBIhBTETIjJBFDNRIxVhJHFC/9oADAMBAAIRAxEAPwD5VAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAf/9k="


PLATFORM_SULTAN_FONT_B64 = "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"

HOME_HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>ASTROGATE | بوابة التحليل الفلكي</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        @font-face {
            font-family: 'SFSultanBlack';
            src: url('data:font/truetype;base64,{{ sultan_font_b64 }}') format('truetype');
            font-weight: 700;
            font-style: normal;
            font-display: swap;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Tahoma, Arial, sans-serif;
            background:
                radial-gradient(circle at top left, rgba(212,175,106,.18), transparent 30%),
                linear-gradient(180deg, #160d22 0%, #241432 48%, #170d21 100%);
            color: #2d2926;
            line-height: 1.8;
        }
        .page {
            width: 100%;
            max-width: 760px;
            margin: 0 auto;
            padding: 14px 14px 26px;
        }
        .brand-card,
        .chart-card {
            background: #f7f1e4;
            border: 1px solid rgba(197, 172, 125, .72);
            border-radius: 24px;
            box-shadow: 0 18px 35px rgba(0,0,0,.22);
            overflow: hidden;
            position: relative;
        }
        .brand-card { padding: 18px 16px 18px; }
        .brand-title {
            text-align: center;
            padding: 4px 0 0;
        }
        .brand-title h1 {
            margin: 0;
            font-family: Impact, Haettenschweiler, 'Arial Black', Tahoma, sans-serif;
            font-size: 42px;
            letter-spacing: 3px;
            line-height: 1;
            color: #0c0a08;
            font-weight: 900;
        }
        .brand-title h2 {
            margin: 8px 0 0;
            font-family: 'SFSultanBlack', Tahoma, Arial, sans-serif;
            font-size: 36px;
            line-height: 1.35;
            color: #15110e;
            font-weight: 700;
            letter-spacing: 0;
        }
        .identity-strip {
            margin: 16px 4px 10px;
            display: grid;
            grid-template-columns: 118px 1fr;
            gap: 14px;
            align-items: stretch;
            direction: ltr;
        }
        .brand-logo-box {
            width: 112px;
            height: 112px;
            background: #050505;
            border-radius: 50%;
            border: 2px solid #b99a5b;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            box-shadow: 0 5px 14px rgba(0,0,0,.15);
            margin: 0 auto;
        }
        .brand-logo {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            border-radius: 50%;
        }
        .tagline-box {
            direction: rtl;
            background: rgba(255,255,255,.64);
            border: 1px solid rgba(224, 210, 185, .9);
            border-radius: 17px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 10px 12px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.55);
        }
        .tagline-box .supervisor {
            font-size: 20px;
            color: #111;
            font-weight: 800;
            margin-bottom: 8px;
        }
        .tagline-box .motto {
            font-family: 'SFSultanBlack', Tahoma, Arial, sans-serif;
            font-size: 29px;
            color: #17120e;
            font-weight: 700;
            letter-spacing: 0;
            line-height: 1.35;
        }
        .tools-title {
            margin: 18px 4px 12px;
            text-align: right;
            color: #3a3128;
            font-size: 20px;
            font-weight: 800;
        }
        .tool-list {
            display: grid;
            gap: 12px;
        }
        .tool-item {
            background: rgba(255,255,255,.78);
            border: 1px solid rgba(222, 212, 196, .9);
            border-radius: 16px;
            padding: 13px 14px;
            min-height: 70px;
            text-decoration: none;
            color: #191410;
            display: grid;
            grid-template-columns: 40px 1fr auto;
            gap: 12px;
            align-items: center;
            box-shadow: 0 4px 10px rgba(0,0,0,.035);
        }
        .tool-icon {
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            color: #8b6f47;
            border-radius: 50%;
            background: #f4ecd9;
        }
        .tool-text {
            text-align: right;
            font-size: 21px;
            font-weight: 800;
            letter-spacing: .3px;
        }
        .tool-badge {
            justify-self: start;
            min-width: 74px;
            text-align: center;
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 14px;
            font-weight: 700;
            color: #5b4f43;
            background: #e8ddca;
        }
        .tool-badge.active { background: #e8f5df; color: #385d2d; }
        .tool-badge.open { background: #e5f2da; color: #346030; }
        .chart-card {
            margin-top: 24px;
            padding: 18px;
        }
        .chart-card h3 {
            margin: 0 0 12px;
            font-size: 24px;
            color: #17120e;
            text-align: center;
            letter-spacing: 1px;
        }
        .chart-stage {
            background: #070707;
            border-radius: 20px;
            padding: 12px;
            min-height: 260px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        .chart-stage svg {
            max-width: 100%;
            width: 320px;
            height: auto;
            display: block;
        }
        .planet-summary {
            margin-top: 12px;
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 4px 6px;
            direction: rtl;
            align-items: start;
        }
        .planet-summary span {
            background: transparent;
            border: 0;
            border-radius: 0;
            padding: 2px 1px;
            color: #3c3027;
            text-align: center;
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            line-height: 1.25;
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
        }
        .planet-summary b {
            display: block;
            font-size: 11px;
            font-weight: 900;
            line-height: 1.15;
            color: #2d251f;
        }
        .planet-summary small {
            display: block;
            margin-top: 2px;
            font-size: 10px;
            font-weight: 700;
            line-height: 1.15;
            color: #5f4a36;
            direction: rtl;
        }
        .footer {
            margin: 14px auto 0;
            text-align: center;
            color: #d9c7a7;
            font-size: 13px;
        }
        @media (max-width: 620px) {
            .page { padding: 12px 10px 24px; }
            .brand-card { border-radius: 22px; padding: 14px 12px; }
            .brand-title { padding: 2px 0 0; }
            .brand-title h1 { font-size: 34px; letter-spacing: 2px; }
            .brand-title h2 { font-size: 32px; margin-top: 7px; }
            .identity-strip { grid-template-columns: 104px 1fr; gap: 10px; margin: 14px 0 8px; }
            .brand-logo-box { width: 104px; height: 104px; }
            .tagline-box .supervisor { font-size: 18px; }
            .tagline-box .motto { font-size: 27px; }
            .tools-title { font-size: 19px; margin-top: 16px; }
            .tool-item { min-height: 66px; padding: 12px; grid-template-columns: 36px 1fr auto; }
            .tool-icon { width: 30px; height: 30px; font-size: 19px; }
            .tool-text { font-size: 19px; }
            .tool-badge { min-width: 64px; padding: 5px 8px; font-size: 13px; }
            .planet-summary { gap: 4px 5px; }
            .planet-summary b { font-size: 10.5px; }
            .planet-summary small { font-size: 9.5px; }
        }
        @media (max-width: 430px) {
            .brand-title h1 { font-size: 30px; }
            .brand-title h2 { font-size: 29px; }
            .identity-strip { grid-template-columns: 92px 1fr; }
            .brand-logo-box { width: 92px; height: 92px; }
            .tagline-box .supervisor { font-size: 16px; }
            .tagline-box .motto { font-size: 24px; }
            .tool-text { font-size: 18px; }
            .planet-summary { gap: 3px 4px; }
            .planet-summary b { font-size: 10px; }
            .planet-summary small { font-size: 9px; }
        }
    </style>
</head>
<body>
<div class="page">
    <section class="brand-card">
        <div class="brand-title">
            <h1>ASTROGATE</h1>
            <h2>بوابة التحليل الفلكي</h2>
        </div>

        <div class="identity-strip">
            <div class="brand-logo-box">
                <img class="brand-logo" src="data:image/jpeg;base64,{{ logo_b64 }}" alt="astrologer.ab">
            </div>
            <div class="tagline-box">
                <div class="supervisor">بإشراف الخبير الفلكي عباس الشباني</div>
                <div class="motto">رؤى كونية وحكمة خالدة</div>
            </div>
        </div>

        <div class="tools-title">أدوات المنصة</div>
        <div class="tool-list">
            <a class="tool-item" href="/profile">
                <span class="tool-icon">☉</span>
                <span class="tool-text">بياناتي الفلكية</span>
                <span class="tool-badge active">أساسي</span>
            </a>
            <a class="tool-item" href="/natal">
                <span class="tool-icon">◉</span>
                <span class="tool-text">قراءة الخريطة</span>
                <span class="tool-badge open">متاح</span>
            </a>
            <a class="tool-item" href="/health">
                <span class="tool-icon">✚</span>
                <span class="tool-text">المؤشرات الصحية</span>
                <span class="tool-badge open">متاح</span>
            </a>
            <a class="tool-item" href="/forecast">
                <span class="tool-icon">☽</span>
                <span class="tool-text">التوقعات الشخصية</span>
                <span class="tool-badge">قريبًا</span>
            </a>
            <a class="tool-item" href="/midpoints">
                <span class="tool-icon">✦</span>
                <span class="tool-text">نقاط المنتصف</span>
                <span class="tool-badge">قريبًا</span>
            </a>
            <a class="tool-item" href="/compatibility">
                <span class="tool-icon">♡</span>
                <span class="tool-text">توافق العلاقات</span>
                <span class="tool-badge">قريبًا</span>
            </a>
            <a class="tool-item" href="/marriage">
                <span class="tool-icon">♃</span>
                <span class="tool-text">توقيت الزواج</span>
                <span class="tool-badge">قريبًا</span>
            </a>
            <a class="tool-item" href="/rectification">
                <span class="tool-icon">◷</span>
                <span class="tool-text">تصحيح الطالع</span>
                <span class="tool-badge">قريبًا</span>
            </a>
            <a class="tool-item" href="/articles">
                <span class="tool-icon">✍</span>
                <span class="tool-text">المقالات الفلكية</span>
                <span class="tool-badge">قريبًا</span>
            </a>
        </div>
    </section>

    <section class="chart-card">
        <h3>الخريطة الفلكية المختصرة</h3>
        <div class="chart-stage">{{ chart_svg|safe }}</div>
        <div class="planet-summary">{{ planet_summary|safe }}</div>
    </section>

    <div class="footer">جميع الحقوق محفوظة للمطور astrologer.ab@</div>
</div>
</body>
</html>
"""

PROFILE_HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>بياناتي الفلكية</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {font-family: Tahoma, Arial, sans-serif; background:#f4f1ea; margin:0; color:#2d2926; line-height:1.9;}
        .container {max-width:850px; margin:0 auto; padding:18px;}
        .card {background:#fffdf8; border:1px solid #ded4c4; border-radius:18px; padding:18px; box-shadow:0 2px 8px rgba(0,0,0,.05); margin-bottom:14px;}
        h1,h2 {color:#3b2f2f; margin-top:0; text-align:center;}
        label {display:block; margin-bottom:5px; font-weight:bold;}
        input,select {width:100%; box-sizing:border-box; padding:10px; border-radius:10px; border:1px solid #c8bda9; background:#fff; font-size:16px;}
        .grid {display:grid; grid-template-columns:repeat(3,1fr); gap:12px;}
        .grid2 {display:grid; grid-template-columns:repeat(2,1fr); gap:12px;}
        .buttons {display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;}
        button,.btn {border:none; border-radius:12px; padding:12px 18px; font-size:16px; cursor:pointer; text-decoration:none; text-align:center; font-weight:bold;}
        button {background:#6f4e37; color:white; flex:1;}
        .btn {background:#d8c7ad; color:#2d2926; flex:1;}
        .nav {display:flex; justify-content:center; gap:8px; flex-wrap:wrap; margin:10px 0 16px;}
        .nav a {background:#fffdf8; border:1px solid #ded4c4; color:#5a3f2a; text-decoration:none; padding:8px 12px; border-radius:999px; font-weight:bold;}
        .hidden {display:none;}
        .success {background:#eaf5e8; border:1px solid #b8d8b4; color:#2f5d35; padding:10px; border-radius:12px; text-align:center; font-weight:bold;}
        .muted {color:#6d6259; font-size:14px;}
        @media(max-width:800px){.grid,.grid2{grid-template-columns:1fr;}}
    </style>
    <script>
        async function loadCitiesForCountry() {
            const countrySelect = document.getElementById("country_code");
            const citySelect = document.getElementById("city_select");
            const manualBox = document.getElementById("manual_city_box");
            const manualInput = document.getElementById("city_manual");
            const selectedCountry = countrySelect.value;
            citySelect.innerHTML = "";
            const loadingOption = document.createElement("option");
            loadingOption.value = "";
            loadingOption.textContent = "جاري تحميل المدن...";
            citySelect.appendChild(loadingOption);
            try {
                const response = await fetch("/api/cities?country_code=" + encodeURIComponent(selectedCountry));
                const data = await response.json();
                citySelect.innerHTML = "";
                data.cities.forEach(function(cityName) {
                    const option = document.createElement("option");
                    option.value = cityName;
                    option.textContent = cityName;
                    citySelect.appendChild(option);
                });
                const other = document.createElement("option");
                other.value = "__manual__";
                other.textContent = "مدينة أخرى / أكتبها يدويًا";
                citySelect.appendChild(other);
                const currentCity = citySelect.getAttribute("data-selected");
                if (currentCity) {
                    let found = false;
                    for (let i = 0; i < citySelect.options.length; i++) {
                        if (citySelect.options[i].value === currentCity) { citySelect.value = currentCity; found = true; break; }
                    }
                    if (!found) { citySelect.value = "__manual__"; manualBox.classList.remove("hidden"); manualInput.value = currentCity; }
                }
                toggleManualCity();
            } catch (e) { toggleManualCity(); }
        }
        function toggleManualCity() {
            const citySelect = document.getElementById("city_select");
            const manualBox = document.getElementById("manual_city_box");
            const manualInput = document.getElementById("city_manual");
            if (citySelect.value === "__manual__") { manualBox.classList.remove("hidden"); manualInput.required = true; }
            else { manualBox.classList.add("hidden"); manualInput.required = false; manualInput.value = ""; }
        }
        document.addEventListener("DOMContentLoaded", function() {
            const countrySelect = document.getElementById("country_code");
            const citySelect = document.getElementById("city_select");
            if (countrySelect && citySelect) {
                if (countrySelect.value) loadCitiesForCountry();
                countrySelect.addEventListener("change", function() { citySelect.setAttribute("data-selected", ""); document.getElementById("city_manual").value = ""; loadCitiesForCountry(); });
                citySelect.addEventListener("change", toggleManualCity);
            }
        });
    </script>
</head>
<body>
<div class="container">
    <h1>بياناتي الفلكية</h1>
    <div class="nav"><a href="/">الرئيسية</a><a href="/profile">بياناتي الفلكية</a><a href="/natal">قراءة الخريطة</a></div>
    {% if saved %}<div class="success">تم حفظ البيانات. يمكنك الآن استخدام تطبيق قراءة الخريطة وبقية التطبيقات لاحقًا.</div>{% endif %}
    <div class="card">
        <form method="post" action="/profile" autocomplete="off">
            <div class="grid2">
                <div><label>الاسم</label><input name="name" value="{{ form.name }}" required></div>
                <div><label>الجنس</label><select name="gender" required><option value="" disabled {% if not form.gender %}selected{% endif %}>اختر الجنس</option><option value="ذكر" {% if form.gender == "ذكر" %}selected{% endif %}>ذكر</option><option value="أنثى" {% if form.gender == "أنثى" %}selected{% endif %}>أنثى</option></select></div>
            </div>
            <div class="grid">
                <div><label>سنة الميلاد</label><input type="number" name="year" value="{{ form.year }}" required></div>
                <div><label>شهر الميلاد</label><input type="number" name="month" value="{{ form.month }}" min="1" max="12" required></div>
                <div><label>يوم الميلاد</label><input type="number" name="day" value="{{ form.day }}" min="1" max="31" required></div>
            </div>
            <div class="grid2">
                <div><label>ساعة الميلاد</label><input type="number" name="hour" value="{{ form.hour }}" min="0" max="23" required><p class="muted">بنظام 24 ساعة.</p></div>
                <div><label>دقيقة الميلاد</label><input type="number" name="minute" value="{{ form.minute }}" min="0" max="59" required></div>
            </div>
            <div class="grid2">
                <div>
                    <label>فرق التوقيت عند الولادة GMT</label>
                    <select name="timezone_offset" required>
                        <option value="" disabled {% if not form.timezone_offset %}selected{% endif %}>اختر فرق التوقيت</option>
                        {% for tz in timezone_options %}
                            <option value="{{ tz.value }}" {% if form.timezone_offset == tz.value %}selected{% endif %}>{{ tz.label }}</option>
                        {% endfor %}
                    </select>
                    <p class="muted">مثال: العراق والسعودية GMT +3.</p>
                </div>
            </div>
            <div class="grid">
                <div><label>الدولة</label><select id="country_code" name="country_code" required><option value="" disabled {% if not form.country_code %}selected{% endif %}>اختر الدولة</option>{% for c in countries %}<option value="{{ c.code }}" {% if form.country_code == c.code %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
                <div><label>المدينة</label><select id="city_select" name="city_select" data-selected="{{ form.city }}" required><option value="" disabled {% if not form.city %}selected{% endif %}>اختر المدينة</option>{% for city_name in city_suggestions %}<option value="{{ city_name }}" {% if form.city == city_name %}selected{% endif %}>{{ city_name }}</option>{% endfor %}<option value="__manual__">مدينة أخرى / أكتبها يدويًا</option></select><div id="manual_city_box" class="hidden" style="margin-top:8px;"><input id="city_manual" name="city_manual" value="{{ form.city_manual }}" placeholder="اكتب اسم المدينة هنا"></div></div>
                <div><label>نظام البيوت</label><select name="house_system"><option value="P" {% if form.house_system == "P" or not form.house_system %}selected{% endif %}>Placidus</option><option value="W" {% if form.house_system == "W" %}selected{% endif %}>Whole Sign</option></select></div>
            </div>
            <div class="buttons"><button type="submit">حفظ بياناتي</button><a class="btn" href="/natal">استخدامها في قراءة الخريطة</a><a class="btn" href="/clear-profile">مسح البيانات</a></div>
        </form>
    </div>
</div>
</body>
</html>
"""

COMING_SOON_HTML = r"""
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>{{ title }}</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:Tahoma,Arial,sans-serif;background:#f4f1ea;margin:0;color:#2d2926;line-height:1.9}.container{max-width:800px;margin:0 auto;padding:18px}.card{background:#fffdf8;border:1px solid #ded4c4;border-radius:18px;padding:24px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.05)}a{display:inline-block;background:#6f4e37;color:#fff;text-decoration:none;padding:10px 14px;border-radius:12px;font-weight:bold;margin:6px}</style></head><body><div class="container"><div class="card"><h1>{{ title }}</h1><p>هذا القسم موجود ضمن هيكل المنصة، وسيتم ربط التطبيق الخاص به لاحقًا.</p><a href="/">العودة للرئيسية</a><a href="/profile">بياناتي الفلكية</a></div></div></body></html>
"""


# ============================================================
# Flask
# ============================================================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "astrologerab-platform-secret")


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



def build_timezone_options() -> List[Dict[str, str]]:
    """قائمة فروق التوقيت اليدوية عن GMT لاستخدامها عند إعداد الخريطة."""
    values = [
        -12, -11, -10, -9, -8, -7, -6, -5, -4, -3.5, -3, -2, -1,
        0, 1, 2, 3, 3.5, 4, 4.5, 5, 5.5, 5.75, 6, 6.5, 7, 8,
        9, 9.5, 10, 11, 12, 13, 14
    ]
    options = []
    for v in values:
        sign = "+" if v >= 0 else "-"
        av = abs(float(v))
        hours = int(av)
        minutes = int(round((av - hours) * 60))
        value = str(v).rstrip('0').rstrip('.') if isinstance(v, float) else str(v)
        label = f"GMT {sign}{hours}"
        if minutes:
            label += f":{minutes:02d}"
        common = {
            "3": "العراق / السعودية / الكويت / قطر / البحرين / اليمن",
            "4": "الإمارات / عُمان",
            "2": "مصر / الأردن / لبنان / سوريا شتاءً",
            "0": "غرينتش / لندن شتاءً",
        }.get(value, "")
        if common:
            label += f" - {common}"
        options.append({"value": value, "label": label})
    return options


def get_selected_timezone_offset(data: Dict[str, str], city_info: Dict[str, object], year: int, month: int, day: int, hour: int, minute: int) -> float:
    """يعطي أولوية لفرق التوقيت الذي يختاره المستخدم، ثم يرجع لحساب المدينة عند تركه فارغًا."""
    raw = str(data.get("timezone_offset", "")).strip()
    if raw:
        try:
            return float(raw)
        except Exception:
            pass
    tz_name = str(city_info.get("timezone", ""))
    return timezone_offset_for_birth(tz_name, year, month, day, hour, minute)


def default_form() -> Dict[str, str]:
    return {
        "name": "",
        "gender": "",
        "year": "",
        "month": "",
        "day": "",
        "hour": "",
        "minute": "",
        "timezone_offset": "",
        "country_code": "",
        "city": "",
        "city_select": "",
        "city_manual": "",
        "house_system": "P",
    }


def form_from_session() -> Dict[str, str]:
    form = default_form()
    saved = session.get("astro_profile", {})
    if isinstance(saved, dict):
        for key in form.keys():
            if key in saved:
                form[key] = str(saved.get(key, ""))
        if not form.get("city_select") and form.get("city"):
            form["city_select"] = form["city"]
    return form


def save_profile_from_form(form: Dict[str, str]) -> None:
    city_choice = form.get("city_select", "").strip()
    city_manual = form.get("city_manual", "").strip()
    city_input = city_manual if city_choice == "__manual__" else city_choice
    form["city"] = city_input
    form["city_select"] = city_choice
    session["astro_profile"] = {k: str(form.get(k, "")) for k in default_form().keys()}


def profile_is_complete() -> bool:
    saved = session.get("astro_profile", {})
    if not isinstance(saved, dict):
        return False
    needed = ["name", "gender", "year", "month", "day", "hour", "minute", "timezone_offset", "country_code", "city", "house_system"]
    return all(str(saved.get(k, "")).strip() for k in needed)


@app.route("/api/cities")
def api_cities():
    country_code = request.args.get("country_code", "")
    cities = city_suggestions_for_country(country_code)

    # ضمان ظهور أهم المدن العراقية أولًا حتى لو تعطلت مكتبة المدن أو تأخرت.
    if country_code == "IQ":
        priority = [
            "بغداد", "النجف", "كربلاء", "الديوانية", "الشامية", "البصرة",
            "الموصل", "كركوك", "أربيل", "السليمانية", "الناصرية", "الحلة",
            "الرمادي", "العمارة", "السماوة", "الكوت", "بعقوبة", "تكريت",
            "دهوك", "الفلوجة", "سامراء"
        ]
        merged = []
        for x in priority + cities:
            if x not in merged:
                merged.append(x)
        cities = merged

    return jsonify({"cities": cities})



def zodiac_wheel_svg(positions: Optional[Dict[str, BodyPosition]] = None, angles: Optional[Dict[str, float]] = None) -> str:
    """يرسم دائرة فلكية مبسطة للواجهة الرئيسية.

    التصحيح المهم في هذه النسخة:
    - AC / الطالع يظهر على يسار الدائرة.
    - MC / وسط السماء يظهر أعلى الدائرة.
    - لا نكتفي بتدوير بسيط للدائرة، بل نستخدم تحويلًا زاويًا مبسطًا
      يثبت النقاط الأربع الرئيسة: AC, IC, DC, MC في مواضعها البصرية
      الشائعة، ويجعل التسلسل يهبط من AC إلى الأسفل.
    """
    signs = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]

    asc_lon = None
    mc_lon = None
    if angles and angles.get("ASC") is not None:
        try:
            asc_lon = float(angles.get("ASC"))
        except Exception:
            asc_lon = None
    if angles and angles.get("MC") is not None:
        try:
            mc_lon = float(angles.get("MC"))
        except Exception:
            mc_lon = None

    def angle_for_lon(lon: float) -> float:
        lon = float(lon) % 360
        if asc_lon is None or mc_lon is None:
            # الوضع الافتراضي قبل إدخال البيانات: الحمل أعلى الدائرة.
            return math.radians(lon - 90)

        # نثبت المحاور الأساسية بصريًا كالتالي:
        # AC = يسار، IC = أسفل، DC = يمين، MC = أعلى.
        # الأهم: التسلسل بعد AC يجب أن ينزل نحو البيت الأول أسفل اليسار،
        # لذلك يكون مسار الطول الصاعد: ASC → IC → DSC → MC → ASC.
        dsc_lon = (asc_lon + 180.0) % 360.0
        ic_lon = (mc_lon + 180.0) % 360.0

        anchor_lons = [asc_lon % 360.0, ic_lon, dsc_lon, mc_lon % 360.0]
        # زوايا SVG: 180 يسار، 90 أسفل، 0 يمين، -90 أعلى، -180 يسار.
        # هذا يجعل التسلسل يهبط من AC إلى الأسفل كما في الخرائط الشائعة.
        anchor_disp = [180.0, 90.0, 0.0, -90.0]

        # نفك الالتفاف بحيث تصبح نقاط ASC→IC→DSC→MC→ASC متصاعدة فلكيًا.
        unwrapped_lons = [anchor_lons[0]]
        for value in anchor_lons[1:]:
            v = value
            while v <= unwrapped_lons[-1]:
                v += 360.0
            unwrapped_lons.append(v)
        unwrapped_lons.append(unwrapped_lons[0] + 360.0)
        unwrapped_disp = anchor_disp + [anchor_disp[0] - 360.0]

        # نضع طول الجرم ضمن نفس الدورة غير الملفوفة.
        lon_u = lon
        while lon_u < unwrapped_lons[0]:
            lon_u += 360.0
        while lon_u > unwrapped_lons[-1]:
            lon_u -= 360.0
        if lon_u < unwrapped_lons[0]:
            lon_u += 360.0

        # استيفاء خطي داخل الربع المناسب بين AC→MC→DC→IC→AC.
        disp = 180.0
        for i in range(4):
            left_lon = unwrapped_lons[i]
            right_lon = unwrapped_lons[i + 1]
            if left_lon <= lon_u <= right_lon:
                span = right_lon - left_lon
                t = 0.0 if span == 0 else (lon_u - left_lon) / span
                disp = unwrapped_disp[i] + t * (unwrapped_disp[i + 1] - unwrapped_disp[i])
                break

        return math.radians(disp % 360.0)

    svg = []
    svg.append('<svg viewBox="0 0 320 320" role="img" aria-label="دائرة الخريطة الفلكية">')
    svg.append('<defs><radialGradient id="g" cx="50%" cy="45%" r="60%"><stop offset="0%" stop-color="#fffaf0"/><stop offset="75%" stop-color="#f3e2c2"/><stop offset="100%" stop-color="#d4af6a"/></radialGradient></defs>')
    svg.append('<circle cx="160" cy="160" r="145" fill="url(#g)" stroke="#8b6f47" stroke-width="2"/>')
    svg.append('<circle cx="160" cy="160" r="112" fill="rgba(255,255,255,.45)" stroke="#b89152" stroke-width="1.5"/>')
    svg.append('<circle cx="160" cy="160" r="66" fill="rgba(255,255,255,.48)" stroke="#d4af6a" stroke-width="1"/>')

    # رموز الأبراج عند منتصف كل برج، وتدور مع الطالع عند توفره.
    for i, sym in enumerate(signs):
        angle = angle_for_lon(i * 30 + 15)
        x = 160 + math.cos(angle) * 128
        y = 160 + math.sin(angle) * 128
        svg.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="20" fill="#4b3427">{sym}</text>')

    # حدود الأبراج الخارجية.
    for i in range(12):
        angle = angle_for_lon(i * 30)
        x1 = 160 + math.cos(angle) * 70
        y1 = 160 + math.sin(angle) * 70
        x2 = 160 + math.cos(angle) * 145
        y2 = 160 + math.sin(angle) * 145
        svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#d0b27a" stroke-width=".8" opacity=".75"/>')

    if positions:
        planet_symbols = {"Sun":"☉","Moon":"☽","Mercury":"☿","Venus":"♀","Mars":"♂","Jupiter":"♃","Saturn":"♄","Uranus":"♅","Neptune":"♆","Pluto":"♇"}
        order = ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"]
        for idx, key in enumerate(order):
            p = positions.get(key)
            if not p:
                continue
            angle = angle_for_lon(float(p.lon))
            r = 89 - (idx % 3) * 8
            x = 160 + math.cos(angle) * r
            y = 160 + math.sin(angle) * r
            svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="#fffdf8" stroke="#6f4e37" stroke-width="1"/>')
            svg.append(f'<text x="{x:.1f}" y="{y+1:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="16" fill="#2c2038">{planet_symbols.get(key,"•")}</text>')

        if angles:
            # AC يسار، DC يمين، MC أعلى، والتسلسل يهبط من AC نحو الأسفل.
            angle_points = [("AC", angles.get("ASC")), ("DC", (float(angles.get("ASC")) + 180) % 360 if angles.get("ASC") is not None else None), ("MC", angles.get("MC"))]
            for label, lon in angle_points:
                if lon is None:
                    continue
                angle = angle_for_lon(float(lon))
                radius = 116 if label in ["AC", "DC"] else 108
                x = 160 + math.cos(angle) * radius
                y = 160 + math.sin(angle) * radius
                svg.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="12" font-weight="700" fill="#7a563d">{label}</text>')
    else:
        svg.append('<text x="160" y="153" text-anchor="middle" font-size="18" font-weight="700" fill="#4b3427">AstroGate</text>')
        svg.append('<text x="160" y="176" text-anchor="middle" font-size="12" fill="#7a6957">أدخل بياناتك لظهور الخريطة</text>')
    svg.append('</svg>')
    return "".join(svg)


def home_preview_from_saved_profile() -> Tuple[str, str]:
    """يعيد SVG وملخص مواقع الكواكب للصفحة الرئيسية."""

    def placeholder_summary() -> str:
        labels = [
            "الشمس", "القمر", "عطارد", "الزهرة", "المريخ", "المشتري",
            "زحل", "أورانوس", "نبتون", "بلوتو", "كايرون", "الطالع"
        ]
        return "".join(f'<span><b>{label}</b><small>—</small></span>' for label in labels)

    if not profile_is_complete():
        return zodiac_wheel_svg(), placeholder_summary()
    try:
        saved = session.get("astro_profile", {})
        year = int(saved.get("year", "0"))
        month = int(saved.get("month", "0"))
        day = int(saved.get("day", "0"))
        hour = int(saved.get("hour", "0"))
        minute = int(saved.get("minute", "0"))
        country_code = str(saved.get("country_code", ""))
        city_input = str(saved.get("city", "") or saved.get("city_select", ""))
        city_info = find_city(country_code, city_input)
        if not city_info:
            raise RuntimeError("city not found")
        lat = float(city_info["lat"])
        lon_geo = float(city_info["lon"])
        timezone = get_selected_timezone_offset(saved, city_info, year, month, day, hour, minute)
        positions, cusps, angles = calculate_chart(year, month, day, hour, minute, timezone, lat, lon_geo, saved.get("house_system", "P") or "P")

        # كايرون لا يدخل ضمن الكواكب العشرة الأساسية في محرك قراءة الخريطة،
        # لذلك نحسبه هنا خصيصًا لملخص الخريطة المختصرة أسفل الدائرة.
        try:
            ensure_asteroid_ephemeris_ready()
            setup_swiss_ephemeris_path()
            chiron_result, chiron_retflag = swe.calc_ut(float(angles["JD_UT"]), swe.CHIRON, swe.FLG_SWIEPH | swe.FLG_SPEED)
            chiron_lon = normalize_deg(float(chiron_result[0]))
            chiron_speed = float(chiron_result[3]) if len(chiron_result) > 3 else 0.0
            chiron_sign, chiron_degree = sign_from_lon(chiron_lon)
            positions["Chiron"] = BodyPosition(
                name_en="Chiron",
                name_ar="كايرون",
                lon=chiron_lon,
                sign=chiron_sign,
                degree=chiron_degree,
                house=house_from_cusps(chiron_lon, cusps),
                term=get_ptolemy_term(chiron_sign, chiron_degree),
                retrograde=chiron_speed < 0,
            )
        except Exception:
            pass

        ordered_keys = [
            "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter",
            "Saturn", "Uranus", "Neptune", "Pluto", "Chiron"
        ]
        parts = []
        for key in ordered_keys:
            p = positions.get(key)
            if p:
                parts.append(f'<span><b>{p.name_ar}</b><small>{p.sign} {format_degree(p.degree)}</small></span>')
            elif key == "Chiron":
                parts.append('<span><b>كايرون</b><small>غير متاح</small></span>')

        asc_sign = str(angles["ASC_sign"])
        asc_degree = float(angles["ASC_degree"])
        # الطالع يبقى آخر عنصر بعد كايرون، ليكتمل السطر الثاني بست خانات.
        parts.append(f'<span><b>الطالع</b><small>{asc_sign} {format_degree(asc_degree)}</small></span>')
        return zodiac_wheel_svg(positions, angles), "".join(parts)
    except Exception:
        summary = '<span>تعذر رسم الخريطة المختصرة مؤقتًا</span><span>أكمل البيانات أو افتح قراءة الخريطة</span>'
        return zodiac_wheel_svg(), summary

@app.route("/")
def home():
    if profile_is_complete():
        saved = session.get("astro_profile", {})
        profile_status = f"تم إدخال البيانات: {saved.get('name', '')}"
    else:
        profile_status = "ابدأ بإدخال بياناتك الفلكية مرة واحدة"
    chart_svg, planet_summary = home_preview_from_saved_profile()
    return render_template_string(
        HOME_HTML,
        profile_status=profile_status,
        logo_b64=PLATFORM_LOGO_B64,
        sultan_font_b64=PLATFORM_SULTAN_FONT_B64,
        chart_svg=chart_svg,
        planet_summary=planet_summary,
    )


@app.route("/profile", methods=["GET", "POST"])
def profile():
    form = form_from_session()
    saved_flag = False
    if request.method == "POST":
        form.update({k: request.form.get(k, form.get(k, "")) for k in form.keys()})
        save_profile_from_form(form)
        saved_flag = True

    countries = build_country_list()
    city_suggestions = city_suggestions_for_country(form.get("country_code", ""))
    return render_template_string(
        PROFILE_HTML,
        form=form,
        saved=saved_flag,
        countries=countries,
        city_suggestions=city_suggestions,
        timezone_options=build_timezone_options(),
    )


@app.route("/clear-profile")
def clear_profile():
    session.pop("astro_profile", None)
    return redirect(url_for("profile"))


def build_natal_report_from_form(form: Dict[str, str]) -> Dict[str, object]:
    """يبني تقرير قراءة الخريطة من البيانات المركزية المحفوظة أو من نموذج natal."""
    name = form["name"].strip() or "صاحب الخريطة"
    gender = form["gender"]
    year = int(form["year"])
    month = int(form["month"])
    day = int(form["day"])
    hour = int(form["hour"])
    minute = int(form["minute"])
    country_code = form["country_code"]

    # المدينة قد تأتي من القائمة أو من حقل الكتابة اليدوية أو من البيانات المركزية.
    city_choice = form.get("city_select", "").strip()
    city_manual = form.get("city_manual", "").strip()
    if city_choice == "__manual__":
        city_input = city_manual
    else:
        city_input = city_choice or form.get("city", "").strip()

    form["city"] = city_input

    city_info = find_city(country_code, city_input)
    if not city_info:
        raise RuntimeError(
            "لم أجد المدينة داخل الدولة المختارة. جرّب كتابة اسم المدينة بالإنكليزية، "
            "مثل Baghdad أو Najaf، أو اختر دولة أخرى إذا كانت المدينة تابعة لها."
        )

    lat = float(city_info["lat"])
    lon_geo = float(city_info["lon"])
    timezone = get_selected_timezone_offset(form, city_info, year, month, day, hour, minute)

    positions, cusps, angles = calculate_chart(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        timezone=timezone,
        lat=lat,
        lon_geo=lon_geo,
        house_system=form["house_system"],
    )

    return build_report(name, gender, positions, cusps, angles, angles.get("JD_UT"))


@app.route("/natal", methods=["GET", "POST"])
def natal():
    form = form_from_session()
    report = None
    error = ""

    # إذا دخل المستخدم بياناته في /profile، تُحسب قراءة الخريطة مباشرة عند فتح /natal.
    should_calculate = request.method == "POST" or profile_is_complete()

    if request.method == "POST":
        form.update({k: request.form.get(k, form.get(k, "")) for k in form.keys()})
        save_profile_from_form(form)

    if should_calculate:
        try:
            report = build_natal_report_from_form(form)
        except Exception as exc:
            error = f"حدث خطأ أثناء الحساب: {exc}"
            report = None

    countries = build_country_list()
    city_suggestions = city_suggestions_for_country(form.get("country_code", ""))

    return render_template_string(
        HTML,
        title=APP_TITLE,
        form=form,
        report=report,
        error=error,
        countries=countries,
        city_suggestions=city_suggestions,
        swisseph_available=SWISSEPH_AVAILABLE,
        geonames_available=GEONAMESCACHE_AVAILABLE,
        timezone_options=build_timezone_options(),
    )




# ============================================================
# تطبيق المؤشرات الصحية الفلكية داخل AstroGate
# ============================================================

HEALTH_SYSTEMS_ORDER = [
    "الجهاز القلبي الوعائي", "الجهاز العصبي", "الجهاز الهضمي", "الجهاز البولي والكلى",
    "الجهاز التنفسي", "العظام والأسنان والمفاصل", "العيون والبصر", "السمع والأذن",
    "الجلد والبشرة", "الغدد والهرمونات", "المناعة والحساسية", "الالتهابات والجراحة",
    "الفحص الوقائي العميق",
]
FERTILITY_SYSTEM = "الخصوبة والإنجاب"
HEALTH_ASPECTS = {"اقتران": 0, "نصف تربيع": 45, "تسديس": 60, "تربيع": 90, "تثليث": 120, "تربيع ونصف": 135, "مقابلة": 180}
HEALTH_HARD_ASPECTS = ["اقتران", "تربيع", "مقابلة", "نصف تربيع", "تربيع ونصف"]
HEALTH_PLANET_AR = {"Sun":"الشمس","Moon":"القمر","Mercury":"عطارد","Venus":"الزهرة","Mars":"المريخ","Jupiter":"المشتري","Saturn":"زحل","Uranus":"أورانوس","Neptune":"نبتون","Pluto":"بلوتو"}
HEALTH_SIGN_RULERS_EN = {"الحمل":"Mars","الثور":"Venus","الجوزاء":"Mercury","السرطان":"Moon","الأسد":"Sun","العذراء":"Mercury","الميزان":"Venus","العقرب":"Mars","القوس":"Jupiter","الجدي":"Saturn","الدلو":"Saturn","الحوت":"Jupiter"}


def health_score_level(score: int) -> str:
    """مستوى موجه للقارئ العادي. لا يعني مرضًا، بل درجة حضور المحور صحيًا في القراءة الفلكية."""
    if score <= 3:
        return "هادئ فلكيًا"
    if score <= 7:
        return "قابل للتأثر"
    if score <= 12:
        return "يحتاج انتباهًا وقائيًا"
    return "محور بارز جدًا"


def health_score_marker(score: int) -> str:
    if score <= 3:
        return "هادئ"
    if score <= 7:
        return "قابل للتأثر"
    if score <= 12:
        return "وقائي"
    return "بارز جدًا"


def health_level_intro(score: int) -> str:
    if score <= 3:
        return "لا يظهر هذا المحور كأولوية فلكية في الخريطة الحالية."
    if score <= 7:
        return "هذا المحور قد يتأثر عند التوتر أو سوء النوم أو اضطراب الروتين."
    if score <= 12:
        return "هذا المحور واضح في الخريطة ويستحق انتباهًا وقائيًا من دون قلق أو تهويل."
    return "هذا المحور بارز جدًا فلكيًا، لذلك لا يُفضّل إهماله عند وجود أعراض واقعية."


def health_add_score(scores: Dict[str, int], reasons: Dict[str, List[str]], system: str, points: int, reason: str) -> None:
    scores[system] = scores.get(system, 0) + int(points)
    reasons.setdefault(system, []).append(reason)


def health_find_aspects(positions: Dict[str, BodyPosition], orb: float = 5.0) -> List[Dict[str, object]]:
    aspects_found: List[Dict[str, object]] = []
    keys = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            p1, p2 = keys[i], keys[j]
            d = angular_distance(float(positions[p1].lon), float(positions[p2].lon))
            for aspect_name, exact_angle in HEALTH_ASPECTS.items():
                orb_value = abs(d - exact_angle)
                if orb_value <= orb:
                    aspects_found.append({"planet1": p1, "planet2": p2, "aspect": aspect_name, "orb": round(orb_value, 2), "distance": round(d, 2)})
                    break
    return aspects_found


def health_aspect_exists(aspects: List[Dict[str, object]], planet_a: str, planet_b: str, aspect_group: Optional[List[str]] = None) -> Optional[Dict[str, object]]:
    for asp in aspects:
        pair = {str(asp["planet1"]), str(asp["planet2"])}
        if pair == {planet_a, planet_b} and (aspect_group is None or str(asp["aspect"]) in aspect_group):
            return asp
    return None


def health_aspects_to_planet(aspects: List[Dict[str, object]], planet_name: str, aspect_group: Optional[List[str]] = None) -> List[Dict[str, object]]:
    return [asp for asp in aspects if planet_name in [str(asp["planet1"]), str(asp["planet2"])] and (aspect_group is None or str(asp["aspect"]) in aspect_group)]


def health_other_planet(asp: Dict[str, object], planet_name: str) -> str:
    return str(asp["planet2"] if asp["planet1"] == planet_name else asp["planet1"])


def health_apply_fertility_rules(positions: Dict[str, BodyPosition], cusps: List[float], aspects: List[Dict[str, object]], scores: Dict[str, int], reasons: Dict[str, List[str]], gender: str) -> None:
    fifth_sign, _ = sign_from_lon(cusps[4])
    fifth_ruler = HEALTH_SIGN_RULERS_EN.get(fifth_sign)
    if fifth_ruler and fifth_ruler in positions:
        fifth_ruler_ar = HEALTH_PLANET_AR.get(fifth_ruler, fifth_ruler)
        health_add_score(scores, reasons, FERTILITY_SYSTEM, 1, f"رأس البيت الخامس في {fifth_sign}، وحاكمه {fifth_ruler_ar}؛ لذلك يُستخدم هذا الكوكب كمفتاح رئيسي لقراءة محور الإنجاب.")
        if house_from_cusps(float(positions[fifth_ruler].lon), cusps) in [6, 8, 12]:
            health_add_score(scores, reasons, FERTILITY_SYSTEM, 3, "حاكم البيت الخامس موجود في بيت صحي أو عميق، وهذا يجعل محور الإنجاب أكثر حضورًا وحساسية في الخريطة.")
        for asp in health_aspects_to_planet(aspects, fifth_ruler, HEALTH_HARD_ASPECTS):
            other = health_other_planet(asp, fifth_ruler)
            if other in ["Saturn", "Neptune", "Pluto", "Mars"]:
                health_add_score(scores, reasons, FERTILITY_SYSTEM, 3, f"حاكم البيت الخامس متصل اتصالًا صعبًا مع {HEALTH_PLANET_AR.get(other, other)}، وهذا يرفع تفعيل محور الإنجاب أو الحاجة إلى الانتباه الوقائي.")

    if gender == "أنثى":
        if positions["Moon"].sign in ["السرطان", "العقرب", "الحوت", "الثور", "العذراء", "الجدي"]:
            health_add_score(scores, reasons, FERTILITY_SYSTEM, 2, "القمر في برج مائي أو ترابي، وهذا يُعد فلكيًا من الدلالات الداعمة لمحور الخصوبة والاستجابة الجسدية.")
        if positions["Venus"].sign in ["الثور", "الميزان", "السرطان", "الحوت"]:
            health_add_score(scores, reasons, FERTILITY_SYSTEM, 2, "الزهرة في موضع داعم نسبيًا، وهذا يعطي مؤشرًا أفضل للتوازن الهرموني والخصوبة الأنثوية.")
        for a,b,pts,reason in [
            ("Moon","Saturn",5,"اتصال صعب بين القمر وزحل في خريطة أنثى قد يشير إلى تأخير أو حساسية في محور الدورة أو الإنجاب."),
            ("Venus","Saturn",5,"اتصال صعب بين الزهرة وزحل في خريطة أنثى يرفع مؤشر متابعة الهرمونات أو المبايض أو تأخر الإنجاب عند وجود أعراض واقعية."),
            ("Moon","Neptune",4,"اتصال صعب بين القمر ونبتون في خريطة أنثى قد يدل على غموض هرموني أو اضطراب سوائل يحتاج متابعة عند ظهور أعراض."),
            ("Venus","Neptune",4,"اتصال صعب بين الزهرة ونبتون في خريطة أنثى قد يشير إلى حساسية هرمونية أو دوائية أو حاجة إلى متابعة إنجابية دقيقة."),
            ("Moon","Pluto",5,"اتصال صعب بين القمر وبلوتو في خريطة أنثى يرفع تفعيل محور الرحم أو السوائل أو الأنسجة المرتبطة بالإنجاب."),
            ("Venus","Pluto",5,"اتصال صعب بين الزهرة وبلوتو في خريطة أنثى يرفع تفعيل محور المبايض والجهاز التناسلي من زاوية وقائية."),
        ]:
            if health_aspect_exists(aspects, a, b, HEALTH_HARD_ASPECTS): health_add_score(scores, reasons, FERTILITY_SYSTEM, pts, reason)
    elif gender == "ذكر":
        if positions["Mars"].sign in ["الحمل", "العقرب", "الجدي", "الأسد"]:
            health_add_score(scores, reasons, FERTILITY_SYSTEM, 2, "المريخ في موضع قوي نسبيًا في خريطة ذكر، وهذا يدعم مؤشر الطاقة الحيوية والقدرة الإنجابية من الناحية الرمزية.")
        if positions["Sun"].sign in ["الحمل", "الأسد", "القوس"]:
            health_add_score(scores, reasons, FERTILITY_SYSTEM, 1, "الشمس في برج ناري، وهذا يدعم مؤشر الحيوية العامة في خريطة الذكر.")
        for a,b,pts,reason in [
            ("Mars","Saturn",5,"اتصال صعب بين المريخ وزحل في خريطة ذكر قد يشير إلى تأخر أو حساسية في الطاقة الإنجابية أو الحاجة إلى فحص خصوبة عند وجود مشكلة واقعية."),
            ("Sun","Saturn",4,"اتصال صعب بين الشمس وزحل في خريطة ذكر قد يدل على ضعف حيوية أو تأخر أو حاجة إلى متابعة صحية عامة مرتبطة بالإنجاب."),
            ("Mars","Neptune",4,"اتصال صعب بين المريخ ونبتون في خريطة ذكر قد يدل على ضعف طاقة أو حالة غير واضحة تحتاج فحصًا عند وجود أعراض."),
            ("Mars","Pluto",5,"اتصال صعب بين المريخ وبلوتو في خريطة ذكر يرفع تفعيل محور الجهاز التناسلي أو الالتهابات العميقة."),
        ]:
            if health_aspect_exists(aspects, a, b, HEALTH_HARD_ASPECTS): health_add_score(scores, reasons, FERTILITY_SYSTEM, pts, reason)



HEALTH_PUBLIC_GUIDE = {
    "الجهاز القلبي الوعائي": {"meaning":"يرتبط هذا المحور بالحيوية العامة، القلب، الدورة الدموية، حرارة الجسد، وطريقة استجابة الجسم للضغط.","manifestation":"قد يظهر عند التفعيل على شكل إجهاد سريع، توتر جسدي، اضطراب في الإيقاع اليومي، أو حساسية تجاه الانفعال والضغط.","advice":"راقب ضغط الحياة اليومي، خفف التوتر، ولا تؤجل الفحص الطبي عند وجود خفقان أو ألم أو تعب متكرر."},
    "الجهاز العصبي": {"meaning":"يرتبط هذا المحور بالأعصاب، التفكير الزائد، التوتر الذهني، النوم، سرعة الاستجابة، وحساسية الجسم للمنبهات.","manifestation":"قد يظهر عند الضغط كقلق، أرق، توتر، تنميل، إرهاق ذهني، أو صعوبة في تهدئة التفكير.","advice":"نظّم النوم، خفف المنبهات، امنح الجسم فترات هدوء، وراجع الطبيب عند استمرار الأعراض العصبية."},
    "الجهاز الهضمي": {"meaning":"يرتبط هذا المحور بالمعدة، الهضم، الغذاء، السوائل، واستجابة البطن للحالة النفسية والروتين اليومي.","manifestation":"قد يظهر مع التوتر أو اضطراب الطعام على شكل تهيج، ثقل، حموضة، انتفاخ، أو حساسية غذائية.","advice":"نظّم مواعيد الطعام، راقب ما يهيج المعدة، وراجع الطبيب عند تكرر الألم أو اضطراب الهضم."},
    "الجهاز البولي والكلى": {"meaning":"يرتبط هذا المحور بالسوائل، الكلى، التوازن الداخلي، التنقية، وأحيانًا أثر الجفاف أو الأملاح.","manifestation":"قد يظهر عند الإهمال كاحتباس سوائل، جفاف، اضطراب أملاح، أو حساسية في محور الكلى والبول.","advice":"اهتم بالماء والتوازن الغذائي، ولا تؤجل التحاليل عند وجود ألم أو حرقة أو تغير واضح في البول."},
    "الجهاز التنفسي": {"meaning":"يرتبط هذا المحور بالتنفس، الصدر، الشعب، الحساسية التنفسية، وطريقة تفاعل الجسم مع الهواء والقلق.","manifestation":"قد يظهر كحساسية، ضيق، سعال متكرر، أو تأثر التنفس مع التوتر والبيئة.","advice":"انتبه للغبار والتدخين والبرد، وراجع الطبيب عند استمرار ضيق التنفس أو السعال."},
    "العظام والأسنان والمفاصل": {"meaning":"يرتبط هذا المحور بالعظام، الأسنان، المفاصل، الجفاف، التصلب، وتأخر التعافي عند الإجهاد.","manifestation":"قد يظهر كألم متكرر، تيبس، تعب في المفاصل، حساسية أسنان، أو حاجة إلى دعم غذائي وفحوصات وقائية.","advice":"اهتم بالحركة المناسبة، الماء، التغذية، وفحوصات العظام والأسنان عند وجود أعراض متكررة."},
    "العيون والبصر": {"meaning":"يرتبط هذا المحور بالبصر، إجهاد العين، الضوء، التركيز، وحساسية العين مع التعب أو الجفاف.","manifestation":"قد يظهر كإجهاد بصري، جفاف، صداع مرتبط بالنظر، أو حساسية للضوء.","advice":"خفف إجهاد الشاشات، افحص النظر دوريًا، ولا تؤجل الطبيب عند وجود تشوش أو ألم."},
    "السمع والأذن": {"meaning":"يرتبط هذا المحور بالأذن، السمع، الطنين، التوازن، وحساسية الجهاز السمعي للتوتر.","manifestation":"قد يظهر كطنين، حساسية صوتية، دوخة خفيفة، أو ضغط في الأذن عند التعب.","advice":"انتبه للأصوات العالية، وراجع الطبيب عند استمرار الطنين أو الدوخة أو ضعف السمع."},
    "الجلد والبشرة": {"meaning":"يرتبط هذا المحور بالجلد، الجفاف، الحساسية، المظهر الخارجي، وتأثر البشرة بالضغط والغذاء.","manifestation":"قد يظهر كجفاف، حكة، تحسس، تهيج، أو بطء في تحسن الجلد عند الإجهاد.","advice":"اهتم بالماء، النوم، الغذاء، وتابع طبيب الجلدية عند استمرار الحساسية أو التغيرات."},
    "الغدد والهرمونات": {"meaning":"يرتبط هذا المحور بالتوازن الهرموني، السوائل، المزاج الجسدي، والدورات الحيوية الداخلية.","manifestation":"قد يظهر كتقلب طاقة، اضطراب نوم، حساسية سوائل، أو تغيرات تحتاج تحليلًا عند وجود أعراض.","advice":"لا تفسر الأعراض هرمونيًا وحدك؛ التحاليل الطبية هي الفيصل عند وجود تعب أو تغير مستمر."},
    "المناعة والحساسية": {"meaning":"يرتبط هذا المحور بالمناعة، الحساسية، الأدوية، التعب غير الواضح، وردود الفعل تجاه البيئة والطعام.","manifestation":"قد يظهر كحساسية متكررة، تعب غامض، تأثر بالأدوية، أو أعراض تتغير حسب الضغط والنوم.","advice":"راقب تكرار الأعراض، تجنب الإفراط في الأدوية دون استشارة، واهتم بالنوم والغذاء."},
    "الالتهابات والجراحة": {"meaning":"يرتبط هذا المحور بالالتهاب، الحرارة، الألم الحاد، الجروح، التدخلات العلاجية، وردود الفعل السريعة للجسم.","manifestation":"قد يظهر كقابلية للالتهاب، ألم مفاجئ، إصابات، أو حاجة لعلاج حاسم عند التفعيل.","advice":"لا تهمل الألم الحاد أو الالتهاب المتكرر، واطلب المشورة الطبية سريعًا عند ظهور علامات قوية."},
    "الفحص الوقائي العميق": {"meaning":"يرتبط هذا المحور بالمتابعة العميقة، الفحوصات الوقائية، الأمور الخفية أو المزمنة التي تحتاج رصدًا لا خوفًا.","manifestation":"قد يظهر كأعراض غير واضحة، تعب متكرر، أو حاجة لمعرفة السبب بدل الاكتفاء بالمسكنات.","advice":"عند تكرار الأعراض، الأفضل إجراء فحص منظم بدل التوقع أو التأجيل."},
    "الخصوبة والإنجاب": {"meaning":"هذا محور حيوي خاص، ولا يُقرأ كمرض. ارتفاعه يعني حضور موضوع الخصوبة أو الأبناء أو الطاقة الحيوية في الخريطة.","manifestation":"قد يظهر كاهتمام أو تفعيل لموضوع الإنجاب، أو حاجة لمتابعة وقائية فقط عند وجود تأخر أو أعراض واقعية.","advice":"لا يُفهم هذا المحور كحكم على القدرة الإنجابية. الفحوصات الطبية وحدها تحدد الحالة الواقعية."},
}


def health_public_row(system: str, score: int, reasons: List[str]) -> Dict[str, object]:
    guide = HEALTH_PUBLIC_GUIDE.get(system, {"meaning":"هذا محور صحي يقرأ ضمن الخريطة بصورة رمزية.","manifestation":"قد يظهر عند الضغط أو التفعيل الفلكي بحسب طبيعة الخريطة.","advice":"تعامل معه كإشارة وقائية لا كتشخيص طبي."})
    percent = 12 if score <= 3 else 38 if score <= 7 else 68 if score <= 12 else 92
    return {"system": system, "score": int(score), "marker": health_score_marker(score), "level": health_score_level(score), "level_intro": health_level_intro(score), "meaning": guide["meaning"], "manifestation": guide["manifestation"], "advice": guide["advice"], "reasons": reasons or [], "percent": percent}


def health_summary_text(active_rows: List[Dict[str, object]], calm_rows: List[Dict[str, object]]) -> str:
    if not active_rows:
        return "الخريطة لا تُظهر محاور صحية ضاغطة بوضوح في هذه القراءة. هذا لا يعني إلغاء الحاجة الطبية، بل يعني أن المؤشرات الفلكية هادئة نسبيًا، والأفضل الحفاظ على روتين صحي وفحوصات طبيعية عند الحاجة."
    top = active_rows[:3]
    names = "، ".join([str(r["system"]) for r in top])
    return f"أبرز المحاور التي تستحق الانتباه الوقائي في هذه القراءة هي: {names}. هذه دلالات رمزية لا تعني وجود مرض، لكنها تشير إلى مناطق قد تتأثر أكثر عند الضغط أو الإهمال أو التفعيل الفلكي."


def build_health_report_from_form(form: Dict[str, str]) -> Dict[str, object]:
    name = form["name"].strip() or "صاحب الخريطة"
    gender = form["gender"]
    year, month, day = int(form["year"]), int(form["month"]), int(form["day"])
    hour, minute = int(form["hour"]), int(form["minute"])
    city_input = form.get("city", "") or form.get("city_select", "")
    city_info = find_city(form["country_code"], city_input)
    if not city_info:
        raise RuntimeError("لم أجد المدينة داخل الدولة المختارة. راجع بياناتي الفلكية أولًا.")
    timezone = get_selected_timezone_offset(form, city_info, year, month, day, hour, minute)
    positions, cusps, angles = calculate_chart(year, month, day, hour, minute, timezone, float(city_info["lat"]), float(city_info["lon"]), form.get("house_system", "P") or "P")
    aspects = health_find_aspects(positions, orb=5)
    all_systems = HEALTH_SYSTEMS_ORDER + [FERTILITY_SYSTEM]
    scores: Dict[str, int] = {key: 0 for key in all_systems}
    reasons: Dict[str, List[str]] = {key: [] for key in all_systems}
    def h(key: str) -> int:
        return int(positions[key].house or house_from_cusps(float(positions[key].lon), cusps))

    if h("Pluto") == 6:
        health_add_score(scores, reasons, "الفحص الوقائي العميق", 5, "وجود بلوتو في البيت السادس يدل على علل عميقة أو متكررة تحتاج متابعة وقائية.")
        health_add_score(scores, reasons, "الالتهابات والجراحة", 3, "بلوتو في السادس قد يدل على أزمات جسدية أو تدخلات علاجية عميقة.")
    if h("Mars") == 1: health_add_score(scores, reasons, "الالتهابات والجراحة", 4, "وجود المريخ في البيت الأول يرفع قابلية الالتهاب أو الألم أو الإصابات.")
    if positions["Mars"].sign == "السرطان": health_add_score(scores, reasons, "الجهاز الهضمي", 4, "المريخ في السرطان يربط الالتهاب أو التهيج بالمعدة والسوائل والهضم.")
    if h("Neptune") in [8,12]:
        health_add_score(scores, reasons, "المناعة والحساسية", 4, "نبتون في البيت الثامن أو الثاني عشر يدل على حساسية، وهن، أدوية، أو أعراض غامضة.")
        health_add_score(scores, reasons, "الفحص الوقائي العميق", 2, "نبتون في بيت عميق قد يدل على أمور صحية خفية أو صعبة التشخيص.")
    if h("Saturn") in [1,6,8,12]:
        health_add_score(scores, reasons, "العظام والأسنان والمفاصل", 4, "زحل في بيت صحي يرفع دلالة العظام والأسنان والمفاصل والتعب المزمن.")
        health_add_score(scores, reasons, "الجلد والبشرة", 2, "زحل في بيت صحي قد يشير إلى جفاف أو حساسية جلدية أو حاجة إلى عناية طويلة المدى.")
    if h("Moon") == 8:
        health_add_score(scores, reasons, "المناعة والحساسية", 2, "القمر في البيت الثامن يربط السوائل والمزاج الجسدي بالأزمات العميقة.")
        health_add_score(scores, reasons, "الفحص الوقائي العميق", 2, "القمر في الثامن يحتاج متابعة عند تفعيل السوائل أو الهرمونات أو المعدة.")
        health_add_score(scores, reasons, "الغدد والهرمونات", 2, "القمر في البيت الثامن قد يزيد حساسية محور السوائل والهرمونات.")
    if positions["Moon"].sign == "الجدي":
        health_add_score(scores, reasons, "العظام والأسنان والمفاصل", 3, "القمر في الجدي يربط السوائل والتعب الجسدي بالعظام والأسنان والجلد.")
        health_add_score(scores, reasons, "الجلد والبشرة", 2, "القمر في الجدي قد يدل على جفاف أو حساسية جلدية مرتبطة بالتعب أو البرودة.")
    if h("Sun") in [6,8,12]: health_add_score(scores, reasons, "الجهاز القلبي الوعائي", 2, "وجود الشمس في بيت صحي أو عميق يجعل محور الحيوية والقلب والدورة الدموية أكثر حساسية فلكيًا.")
    if h("Mercury") in [3,6,12]:
        health_add_score(scores, reasons, "الجهاز التنفسي", 2, "وجود عطارد في بيت مرتبط بالحركة أو الصحة أو الأمور الخفية قد يرفع حساسية التنفس والأعصاب.")
        health_add_score(scores, reasons, "الجهاز العصبي", 1, "عطارد في بيت حساس يزيد حضور المحور العصبي والذهني في الخريطة.")

    aspect_rules = [
        (("Mars","Saturn"),"العظام والأسنان والمفاصل",5,"اتصال صعب بين المريخ وزحل: دلالة ألم، عظام، أسنان، مفاصل، كسور، أو تأخر شفاء."),(("Mars","Saturn"),"الالتهابات والجراحة",4,"اتصال المريخ بزحل قد يدل على جراحة، إصابة، أو التهاب مع انسداد."),
        (("Sun","Neptune"),"المناعة والحساسية",4,"اتصال صعب بين الشمس ونبتون: وهن، حساسية، تعب غير واضح، أو ضعف مناعة."),(("Sun","Neptune"),"العيون والبصر",3,"اتصال الشمس بنبتون قد يرتبط بضبابية الرؤية أو حساسية الضوء."),
        (("Sun","Saturn"),"العظام والأسنان والمفاصل",3,"اتصال الشمس بزحل قد يدل على تعب مزمن أو ضعف في العظام والظهر."),(("Sun","Saturn"),"العيون والبصر",3,"اتصال الشمس بزحل قد يرفع دلالة إجهاد العين أو الجفاف أو الضعف التدريجي."),(("Sun","Saturn"),"الجهاز القلبي الوعائي",3,"اتصال الشمس بزحل قد يدل فلكيًا على انخفاض الحيوية أو ضغط على محور القلب والدورة الدموية."),
        (("Sun","Mars"),"الجهاز القلبي الوعائي",3,"اتصال صعب بين الشمس والمريخ قد يرفع حرارة الجسد أو التوتر أو سرعة الاستجابة القلبية."),(("Sun","Mars"),"الالتهابات والجراحة",3,"الشمس مع المريخ قد تعطي قابلية للالتهاب أو الإصابات عند التفعيل."),
        (("Sun","Uranus"),"الجهاز القلبي الوعائي",3,"اتصال صعب بين الشمس وأورانوس قد يرمز إلى اضطراب مفاجئ في الحيوية أو النبض أو التوتر الجسدي."),(("Sun","Uranus"),"الجهاز العصبي",2,"الشمس مع أورانوس قد ترفع حساسية الجهاز العصبي والتوتر المفاجئ."),
        (("Mercury","Uranus"),"الجهاز العصبي",4,"اتصال عطارد بأورانوس يدل على توتر عصبي أو كهرباء عصبية أو تنميل."),(("Mercury","Uranus"),"السمع والأذن",3,"اتصال عطارد بأورانوس قد يدل على طنين أو حساسية صوتية مفاجئة."),
        (("Mercury","Saturn"),"الجهاز العصبي",4,"اتصال عطارد بزحل يدل على توتر عصبي مزمن أو بطء في الاستجابة العصبية."),(("Mercury","Saturn"),"السمع والأذن",3,"اتصال عطارد بزحل قد يرفع دلالة ضعف السمع أو الطنين المزمن."),(("Mercury","Saturn"),"الجهاز التنفسي",2,"عطارد مع زحل قد يدل على بطء أو جفاف أو ضيق في المحور التنفسي عند وجود عوامل مساعدة."),
        (("Mercury","Neptune"),"الجهاز العصبي",3,"اتصال عطارد بنبتون يدل على تشوش عصبي أو أعراض غير واضحة."),(("Mercury","Neptune"),"السمع والأذن",3,"اتصال عطارد بنبتون قد يرتبط بطنين أو حساسية صوتية."),(("Mercury","Neptune"),"المناعة والحساسية",2,"عطارد مع نبتون يرفع دلالة الحساسية والتنفس الحساس."),(("Mercury","Neptune"),"الجهاز التنفسي",3,"عطارد مع نبتون قد يدل على حساسية تنفسية أو أعراض متغيرة وغير واضحة."),
        (("Venus","Saturn"),"الجهاز البولي والكلى",4,"اتصال الزهرة بزحل يدل على كلى، جلد، هرمونات، جفاف، أو نقص."),(("Venus","Saturn"),"الجلد والبشرة",3,"اتصال الزهرة بزحل قد يدل على جفاف الجلد أو حساسية مزمنة أو نقص في الترطيب."),(("Venus","Saturn"),"الغدد والهرمونات",2,"الزهرة مع زحل قد ترفع حساسية محور الهرمونات أو التوازن الداخلي."),
        (("Venus","Neptune"),"الجهاز البولي والكلى",3,"اتصال الزهرة بنبتون يدل على سوائل، كلى، هرمونات، أو حساسية."),(("Venus","Neptune"),"المناعة والحساسية",3,"الزهرة مع نبتون ترفع دلالة الحساسية الجلدية أو الدوائية."),(("Venus","Neptune"),"الغدد والهرمونات",3,"الزهرة مع نبتون قد تشير إلى حساسية في المحور الهرموني أو السوائل."),
        (("Venus","Pluto"),"الغدد والهرمونات",3,"اتصال الزهرة ببلوتو يرفع حساسية محور الهرمونات والأنسجة العميقة."),(("Venus","Pluto"),"الفحص الوقائي العميق",2,"الزهرة مع بلوتو قد تشير إلى حاجة لمتابعة وقائية للأنسجة أو الغدد عند وجود أعراض."),
        (("Jupiter","Pluto"),"الفحص الوقائي العميق",5,"اتصال المشتري ببلوتو يدل على نمو زائد أو تحولات عميقة تحتاج متابعة وقائية."),(("Saturn","Pluto"),"الفحص الوقائي العميق",5,"اتصال زحل ببلوتو يدل على دلالة مزمنة عميقة تحتاج فحصًا وقائيًا عند ظهور أعراض."),(("Saturn","Pluto"),"العظام والأسنان والمفاصل",3,"زحل وبلوتو قد يربطان الضغط العميق بالعظام أو الجلد أو التصلب."),
        (("Mars","Pluto"),"الالتهابات والجراحة",5,"اتصال المريخ ببلوتو يدل على التهاب عميق أو ألم شديد أو تدخل علاجي قوي."),(("Mars","Pluto"),"الفحص الوقائي العميق",3,"المريخ مع بلوتو يرفع دلالة التحولات الجسدية العميقة."),
        (("Moon","Neptune"),"المناعة والحساسية",4,"اتصال القمر بنبتون يدل على حساسية، سوائل، نوم، أو تعب غامض."),(("Moon","Neptune"),"الغدد والهرمونات",3,"القمر مع نبتون قد يرفع حساسية السوائل والهرمونات والنوم."),
        (("Moon","Pluto"),"الفحص الوقائي العميق",4,"اتصال القمر ببلوتو يدل على ضغط نفسي جسدي عميق أو تحولات في السوائل والأنسجة."),(("Moon","Pluto"),"الغدد والهرمونات",2,"القمر مع بلوتو قد يرفع حساسية محور الهرمونات والسوائل والأنسجة العميقة."),
        (("Sun","Pluto"),"الفحص الوقائي العميق",4,"اتصال الشمس ببلوتو يدل على تحول عميق في الحيوية والجسد."),(("Sun","Pluto"),"الجهاز القلبي الوعائي",2,"الشمس مع بلوتو قد ترفع حساسية محور الحيوية والقلب والدورة الدموية."),
    ]
    for (a,b), system, pts, reason in aspect_rules:
        if health_aspect_exists(aspects, a, b, HEALTH_HARD_ASPECTS): health_add_score(scores, reasons, system, pts, reason)
    health_apply_fertility_rules(positions, cusps, aspects, scores, reasons, gender)

    for key in scores:
        scores[key] = max(0, int(scores[key]))

    score_rows = []
    for system in HEALTH_SYSTEMS_ORDER + [FERTILITY_SYSTEM]:
        score = scores.get(system, 0)
        score_rows.append(health_public_row(system, score, reasons.get(system, [])))

    active_rows = [r for r in score_rows if int(r["score"]) >= 4]
    active_rows.sort(key=lambda r: int(r["score"]), reverse=True)
    calm_rows = [r for r in score_rows if int(r["score"]) < 4]
    fertility_row = next((r for r in score_rows if r["system"] == FERTILITY_SYSTEM), None)
    health_active_rows = [r for r in active_rows if r["system"] != FERTILITY_SYSTEM]

    planet_rows = [{"name": positions[k].name_ar, "pos": f"{positions[k].sign} {format_degree(positions[k].degree)}", "house": positions[k].house, "motion": "متراجع" if positions[k].retrograde else "مباشر"} for k in ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"]]
    aspect_rows = [{"p1": HEALTH_PLANET_AR.get(str(a["planet1"]), str(a["planet1"])), "p2": HEALTH_PLANET_AR.get(str(a["planet2"]), str(a["planet2"])), "aspect": a["aspect"], "orb": a["orb"]} for a in aspects]
    return {"name": name, "gender": gender, "date": f"{day}/{month}/{year}", "time": f"{hour:02d}:{minute:02d}", "timezone": timezone, "city": city_input, "asc": f"{angles['ASC_sign']} {format_degree(float(angles['ASC_degree']))}", "mc": f"{angles['MC_sign']} {format_degree(float(angles['MC_degree']))}", "summary": health_summary_text(health_active_rows, calm_rows), "score_rows": score_rows, "active_rows": health_active_rows, "calm_rows": calm_rows, "fertility_row": fertility_row, "planet_rows": planet_rows, "aspect_rows": aspect_rows}


HEALTH_HTML = '<!DOCTYPE html>\n<html lang="ar" dir="rtl">\n<head>\n<meta charset="UTF-8">\n<title>المؤشرات الصحية | AstroGate</title>\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<style>\n*{box-sizing:border-box}\nbody{font-family:Tahoma,Arial,sans-serif;background:linear-gradient(180deg,#160d22 0%,#241432 45%,#170d21 100%);margin:0;color:#2d2926;line-height:1.9}\n.container{max-width:900px;margin:0 auto;padding:18px}.card{background:#f7f1e4;border:1px solid rgba(197,172,125,.72);border-radius:22px;padding:18px;margin-bottom:16px;box-shadow:0 14px 28px rgba(0,0,0,.20)}\nh1,h2,h3{margin-top:0;color:#1d1712}.center{text-align:center}.nav{text-align:center;margin:12px 0}.nav a{display:inline-block;background:#fffdf8;border:1px solid #ded4c4;color:#5a3f2a;text-decoration:none;padding:8px 14px;border-radius:999px;font-weight:bold;margin:4px}\n.notice{background:#fff8e8;border:1px solid #dec99d;border-radius:16px;padding:12px}.summary{font-size:17px;font-weight:700;color:#2b2119}.health-card{background:#fffdf8;border:1px solid #e4d8c4;border-radius:18px;padding:15px;margin:12px 0}.health-head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}.level{font-weight:bold;background:#efe5d4;border-radius:999px;padding:5px 12px;color:#4c3a2c}.level.hot{background:#ead9c4;color:#5f301a}.bar{height:34px;background:#e9dfcf;border-radius:999px;overflow:hidden;margin:10px 0 12px;position:relative}.fill{height:100%;background:#8b6f47;border-radius:999px}.percent-label{position:absolute;left:14px;top:50%;transform:translateY(-50%);font-weight:900;font-size:18px;color:#4b3828;direction:ltr}.percent-title{font-weight:bold;background:#f8efe0;border:1px solid #e4d8c4;border-radius:999px;padding:5px 12px;color:#4c3a2c;direction:ltr}.sub{font-weight:bold;color:#5f4936;margin-top:9px}.quiet-list{display:flex;flex-wrap:wrap;gap:8px}.quiet-item{background:#fffdf8;border:1px solid #e4d8c4;border-radius:999px;padding:6px 10px;font-size:14px}.details{margin-top:10px;background:#faf6ee;border:1px solid #eadfce;border-radius:14px;padding:10px}.small-table{width:100%;border-collapse:collapse;background:#fffdf8;border-radius:14px;overflow:hidden}.small-table th,.small-table td{border-bottom:1px solid #e4d8c4;padding:9px;text-align:right}.footer{text-align:center;color:#d9c7a7;font-size:13px;margin-top:14px}@media(max-width:650px){.container{padding:12px}.health-head{display:block}.small-table{font-size:13px}}\n</style></head><body><div class="container">\n<div class="card center"><h1>المؤشرات الصحية الوقائية</h1><p>قراءة فلكية رمزية للمحاور الجسدية الأكثر قابلية للتأثر، بلغة وقائية لا تشخيصية.</p><div class="nav"><a href="/">الرئيسية</a><a href="/profile">بياناتي الفلكية</a><a href="/natal">قراءة الخريطة</a></div></div>\n{% if error %}<div class="card notice"><strong>{{ error }}</strong><br><a href="/profile">إدخال بياناتي الفلكية</a></div>{% elif report %}\n<div class="card"><h2>بيانات الحساب</h2><p><strong>{{ report.name }}</strong> — {{ report.gender }}<br>تاريخ الميلاد: {{ report.date }} — الوقت: {{ report.time }} — GMT {{ \'%+.2f\'|format(report.timezone) }}<br>المدينة: {{ report.city }}<br>الطالع: {{ report.asc }} — MC: {{ report.mc }}</p><div class="notice">هذا التقرير لا يقدم تشخيصًا طبيًا ولا يغني عن الطبيب. ارتفاع المؤشر يعني حضورًا فلكيًا أو قابلية رمزية تحتاج انتباهًا وقائيًا فقط، خاصة عند وجود أعراض واقعية.</div></div>\n<div class="card"><h2>الخلاصة الصحية العامة</h2><p class="summary">{{ report.summary }}</p></div>\n<div class="card"><h2>أبرز المحاور الصحية التي تستحق الانتباه</h2>{% if report.active_rows %}{% for row in report.active_rows %}<div class="health-card"><div class="health-head"><h3>{{ row.system }}</h3><span class="percent-title">{{ row.percent }}%</span><span class="level {% if row.score > 12 %}hot{% endif %}">{{ row.level }}</span></div><div class="bar"><div class="fill" style="width:{{ row.percent }}%"></div><span class="percent-label">{{ row.percent }}%</span></div><p><strong>{{ row.level_intro }}</strong></p><div class="sub">المعنى</div><p>{{ row.meaning }}</p><div class="sub">كيف قد يظهر؟</div><p>{{ row.manifestation }}</p><div class="sub">النصيحة الوقائية</div><p>{{ row.advice }}</p>{% if row.reasons %}<details class="details"><summary>الأسباب الفلكية المختصرة</summary><ul>{% for reason in row.reasons %}<li>{{ reason }}</li>{% endfor %}</ul></details>{% endif %}</div>{% endfor %}{% else %}<p>لا توجد محاور صحية بارزة في هذه القراءة. هذا لا يلغي أهمية الطب والفحوصات، لكنه يعني أن المؤشرات الفلكية هادئة نسبيًا.</p>{% endif %}</div>\n{% if report.fertility_row %}<div class="card"><h2>محور الخصوبة والإنجاب</h2><div class="health-card"><div class="health-head"><h3>{{ report.fertility_row.system }}</h3><span class="percent-title">{{ report.fertility_row.percent }}%</span><span class="level">{{ report.fertility_row.level }}</span></div><div class="bar"><div class="fill" style="width:{{ report.fertility_row.percent }}%"></div><span class="percent-label">{{ report.fertility_row.percent }}%</span></div><p><strong>{{ report.fertility_row.level_intro }}</strong></p><p>{{ report.fertility_row.meaning }}</p><p>{{ report.fertility_row.manifestation }}</p><p>{{ report.fertility_row.advice }}</p>{% if report.fertility_row.reasons %}<details class="details"><summary>الأسباب الفلكية المختصرة</summary><ul>{% for reason in report.fertility_row.reasons %}<li>{{ reason }}</li>{% endfor %}</ul></details>{% endif %}</div></div>{% endif %}\n<div class="card"><h2>المحاور الهادئة فلكيًا</h2><p>هذه المحاور لا تظهر كأولوية فلكية في القراءة الحالية. هذا لا يعني غياب أي احتمال طبي، بل يعني أنها ليست الأكثر بروزًا في الخريطة.</p><div class="quiet-list">{% for row in report.calm_rows %}<span class="quiet-item">{{ row.system }}</span>{% endfor %}</div></div>\n<div class="card"><h2>مواقع الكواكب المستخدمة صحيًا</h2><table class="small-table"><thead><tr><th>الكوكب</th><th>الموقع</th><th>البيت</th><th>الحركة</th></tr></thead><tbody>{% for p in report.planet_rows %}<tr><td>{{ p.name }}</td><td>{{ p.pos }}</td><td>{{ p.house }}</td><td>{{ p.motion }}</td></tr>{% endfor %}</tbody></table></div>\n<div class="card"><h2>الاتصالات الصحية المفحوصة</h2>{% if report.aspect_rows %}<table class="small-table"><thead><tr><th>الكوكب الأول</th><th>الزاوية</th><th>الكوكب الثاني</th><th>الأورب</th></tr></thead><tbody>{% for a in report.aspect_rows %}<tr><td>{{ a.p1 }}</td><td>{{ a.aspect }}</td><td>{{ a.p2 }}</td><td>{{ a.orb }}°</td></tr>{% endfor %}</tbody></table>{% else %}<p>لا توجد اتصالات ضمن الأورب المحدد.</p>{% endif %}</div>\n{% endif %}<div class="footer">جميع الحقوق محفوظة للمطور astrologer.ab@</div></div></body></html>\n'

@app.route("/forecast")
def forecast():
    return render_template_string(COMING_SOON_HTML, title="التوقعات الشخصية")


@app.route("/midpoints")
def midpoints():
    return render_template_string(COMING_SOON_HTML, title="نقاط المنتصف")


@app.route("/compatibility")
def compatibility():
    return render_template_string(COMING_SOON_HTML, title="توافق العلاقات")


@app.route("/marriage")
def marriage():
    return render_template_string(COMING_SOON_HTML, title="توقيت الزواج")


@app.route("/rectification")
def rectification():
    return render_template_string(COMING_SOON_HTML, title="تصحيح الطالع")


@app.route("/health")
def health():
    if not profile_is_complete():
        return render_template_string(HEALTH_HTML, report=None, error="لإظهار المؤشرات الصحية، أدخل بيانات ميلادك أولًا من صفحة بياناتي الفلكية.")
    try:
        report = build_health_report_from_form(form_from_session())
        return render_template_string(HEALTH_HTML, report=report, error="")
    except Exception as exc:
        return render_template_string(HEALTH_HTML, report=None, error=f"حدث خطأ أثناء حساب المؤشرات الصحية: {exc}")


@app.route("/articles")
def articles():
    return render_template_string(COMING_SOON_HTML, title="المقالات الفلكية")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print("تشغيل تطبيق قراءة الخريطة الشخصية V6.0 Railway Final")
    print(f"افتح الرابط المحلي: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
