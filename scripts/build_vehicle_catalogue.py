#!/usr/bin/env python3
"""Build reference/vehicle_catalogue.csv: every make, model and model year a Chicago-area household might insure.

    python scripts/fetch_public_data.py --only vehicles
    python scripts/build_vehicle_catalogue.py

One row per make, model and model year, 1981 (the first model year of the 17-character VIN) to 2026. Sources:

  * EPA/DOE fuel economy data (fueleconomy.gov, vehicles.csv, public domain): every light-duty car, SUV, pickup
    and passenger van sold in the US, by model year, with its size class, drive, engine and fuel. Its data
    begins with model year 1984; for 1981 to 1983 each model EPA lists in 1984 is carried back with its 1984
    class, body, drive and engine (source "EPA 1984, carried back"), so models discontinued before 1984 are
    missing and models introduced in 1984 appear a few years early. Those three model years are rare on the
    road (well under 1% of the cars in Chicago's crashes). Its base
    model names are cleaned (2WD/4WD and trim variants merged, cargo vans, hearses, limousines and test codes
    dropped, battery-electric versions of petrol models split out as their own model).
  * reference/vehicle_supplement.csv: models EPA does not cover because they weigh over 8,500 lb (heavy-duty
    pickups, Hummer H1 and H2, Ford Excursion).
  * City of Chicago Data Portal, Traffic Crashes - Vehicles (2021-2025): how common each make, model and model
    year is. Only vehicles in personal use (or of unknown use, or parked) are counted, so police, taxi, bus,
    delivery and other commercial vehicles do not inflate their models. Crash-involved vehicles are a proxy
    for the vehicles on the road (it over-represents vehicles that crash more and are driven more).
  * reference/vehicle_curation.csv: hand-maintained base prices, theft factors, segments and, for models the
    crash records do not name, a relative-sales prior.

`popularity` is the model's share of that model year's vehicles, smoothed over neighbouring model years. Models
that the crash records never mention keep a small floor weight, so rare models can still be drawn.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
FIRST_YEAR, LAST_YEAR = 1981, 2026
EPA_FIRST_YEAR = 1984           # the first model year in EPA's data; earlier years are carried back from it
PRICE_GROWTH = 1.024            # nominal growth of a model's base price per model year (ASSUMED, from base MSRPs 1997-2024)
PERSONAL_USES = {"PERSONAL", "UNKNOWN/NA", "NOT IN USE", "RIDESHARE SERVICE"}
SMOOTH_TAU = 1.5                # model years; kernel width for smoothing shares across model years
FLOOR_SHARE = 2e-6              # minimum share of a model year for a model the crash records never name
OTHER_SHARE_CAP = 1.5           # an unnamed model gets at most this multiple of its sales-prior share of its make

# ------------------------------------------------------------------------------------------------ EPA cleaning
DROP_MAKES = {"Azure Dynamics", "London Taxi", "Mobility Ventures LLC", "VPG", "Quantum Technologies", "Tecstar, LP",
              "BYD", "Roush Performance", "Saleen Performance", "RUF Automobile", "Shelby", "Mahindra"}
MAKE_FIX = {"Mini": "MINI", "McLaren Automotive": "McLaren", "Bugatti Rimac": "Bugatti", "SRT": "Dodge",
            "STI": "Subaru", "BMW Alpina": "BMW", "INEOS Automotive": "INEOS", "Vinfast": "VinFast",
            "CODA Automotive": "CODA"}
# (make, EPA base model or regex) -> catalogue model name; None drops the rows
RENAME: dict[str, list[tuple[str, str | None]]] = {
    "*": [(r".*\bCargo\b.*", None), (r".*Cab Chassis.*", None), (r".*\b(Hearse|Limo|Limousine|Funeral)\b.*", None),
          (r"^Armored .*", None), (r"^Postal Vehicle$", None)],
    "Acura": [],
    "Aston Martin": [(r"^DB.?7.*|^DB AR1$", "DB7"), (r"^DB12.*", "DB12"), (r"^DBX.*", "DBX"), (r"^Vantage.*", "Vantage")],
    "Audi": [(r"^TT.*", "TT"), (r"^R8.*", "R8"), (r"^RS ?3$", "RS 3"), (r"^S e-tron$|^RS e-tron.*|^e-tron GT$", "e-tron GT"),
             (r"^e-tron S$", "e-tron"), (r"^SQ6 e-tron$", "Q6 e-tron"), (r"^SQ8 e-tron$", "Q8 e-tron"), (r"^Cabriolet$", "Cabriolet")],
    "BMW": [(r"^ActiveHybrid X6$", "X6"), (r"^Active E$", "ActiveE"), (r"^Roadster$", None)],
    "Bentley": [(r"^Continental Flying Spur$", "Flying Spur"), (r"^Continental .*", "Continental")],
    "Buick": [(r"^Lacrosse/Allure$", "LaCrosse"), (r"^Regal/Century$", "Regal")],
    "Cadillac": [(r"^(ATS|CTS|STS|XLR)-V$", r"\1")],
    "Chevrolet": [(r"^[CK]1500 Pickup$", "C/K 1500"), (r"^Pickup 2500$", "C/K 2500"), (r"^S10 Pickup$", "S-10"),
                  (r"^SSR Pickup$", "SSR"), (r"^Lumina/Monte Carlo$", "Lumina"), (r"^TrailBlazer$", "Trailblazer"),
                  (r"^Express Passenger$", "Express"), (r"^Astro Passenger$", "Astro"), (r"^Classic$", "Malibu"),
                  (r"^Van .*", None)],
    "Chrysler": [(r"^Concorde/LHS$", "Concorde"), (r"^New Yorker/LHS$", "LHS"), (r"^Town and Country/.*|^Voyager/Town and Country$", "Town and Country"),
                 (r"^JX/JXI/Limited Convertible$", "Sebring"), (r"^300 SRT8$", "300")],
    "Dodge": [(r"^Caravan/Grand Caravan$", "Grand Caravan"), (r"^Neon/.*", "Neon"), (r"^Dakota Pickup$", "Dakota"),
              (r"^Ram 1500 Pickup$", "Ram 1500"), (r"^B\d.* Wagon$|^Ram Wagon \d+$", "Ram Wagon"), (r"^B\d.* Van$|^Ram Van \d+$", None)],
    "Ferrari": [(r"^Ferrari ", ""), (r"^F1\d\d.*", None), (r"^360 .*", "360"), (r"^456.*", "456"), (r"^458 .*", "458"), (r"^488 .*", "488"),
                (r"^550 .*", "550 Maranello"), (r"^575.*", "575M Maranello"), (r"^599 .*", "599"), (r"^812 .*", "812"),
                (r"^F12.*", "F12"), (r"^296 .*", "296"), (r"^SF90.*", "SF90"), (r"^F355.*", "F355"), (r"^F8 .*", "F8"),
                (r"^California.*", "California"), (r"^Monza SP\d$", "Monza SP"), (r"^Enzo Ferrari$", "Enzo"),
                (r"^F430$", "F430"), (r"^F60 America$", "F60 America")],
    "Ford": [(r"^F150$", "F-150"), (r"^F250$", "F-250"), (r"^F-150 Lightning$", "F-150 Lightning"), (r"^Aerostar Wagon$", "Aerostar"),
             (r"^Aerostar Van$", None), (r"^E\d50 (Club )?Wagon$", "E-Series Wagon"), (r"^E\d50 (Econoline|Van)$", None),
             (r"^Transit T150 Wagon$", "Transit Wagon"), (r"^Th!nk$", "Think City")],
    "GMC": [(r"^Safari Passenger$", "Safari"), (r"^Savana Passenger$", "Savana")],
    "Honda": [],
    "Hummer": [(r"^H3T$", "H3")],
    "Hyundai": [(r"^Accent/Brio$", "Accent")],
    "Infiniti": [],
    "Isuzu": [(r"^Hombre Pickup$", "Hombre"), (r"^i-\d+ .*", "i-Series")],
    "Jaguar": [(r"^S-type$", "S-Type"), (r"^(Vdp|Vanden Plas|Super V8|XJL|XJR)$", "XJ"), (r"^(XK8|XKR)$", "XK")],
    "Jeep": [(r"^Gladiator Pickup$", "Gladiator"), (r"^Liberty/Cherokee$", "Liberty"), (r"^Wrangler/TJ$", "Wrangler")],
    "Kia": [(r"^Sephia/Spectra$", "Sephia")],
    "Lotus": [(r"^Elise/[Ee]xige$", "Elise")],
    "MINI": [(r"^John Cooper Works$", "Cooper"), (r"^MiniE$", "MINI E")],
    "Maserati": [(r"^Coupe.*", "Coupe"), (r"^Gran[Tt]urismo$", "GranTurismo"), (r"^Grancabrio$", "GranCabrio"), (r"^MCPURA$", "MC20")],
    "Maybach": [(r"^Landaulet$", None)],
    "Mazda": [(r"^MX-5( Miata)?$", "MX-5 Miata"), (r"^Protege/.*", "Protege"), (r"^Speed 3$", "Mazdaspeed3"), (r"^B Pickup$", "B-Series"),
              (r"^2$", "Mazda2"), (r"^3$", "Mazda3"), (r"^5$", "Mazda5"), (r"^6$", "Mazda6")],
    "McLaren": [(r"^MSO HS$", None), (r"^(\S+) (Coupe|Spider|Can-Am)$", r"\1")],
    "Mercedes-Benz": [(r"^Metris Passenger$", "Metris"), (r"^B-Class Electric Drive$", "B-Class Electric")],
    "Mercury": [],
    "Mitsubishi": [(r"^3000 GT.*", "3000GT"), (r"^Raider Pickup$", "Raider"), (r"^Nativa$", None)],
    "Nissan": [(r"^350z$", "350Z"), (r"^370z$", "370Z"), (r"^LEAF$", "Leaf"), (r"^Altima / Stanza$", "Altima"), (r"^Sentra/200SX$", "Sentra"),
               (r"^Truck$", "Pickup"), (r"^NV200 .*", None), (r"^Hyper-Mini$|^Altra EV$", None)],
    "Oldsmobile": [(r"^Eighty-Eight.*", "Eighty-Eight")],
    "Plymouth": [(r"^Voyager/Grand Voyager$", "Voyager")],
    "Pontiac": [(r"^Firebird/.*", "Firebird"), (r"^Trans Sport/Montana$", "Montana")],
    "Porsche": [(r"^(Carrera|Turbo|Targa|New 911).*", "911"), (r"^911$", "911")],
    "Ram": [(r"^C/V$", None), (r"^Promaster City$", "ProMaster City")],
    "Rolls-Royce": [(r"^Brooklands/Turbo R$", None), (r"^Corniche/Continental$", "Corniche"), (r"^Silver Spur.*", "Silver Spur")],
    "Saturn": [(r"^L\d.*|^LS$|^LW$", "L-Series"), (r"^S[CLW]$", "S-Series"), (r"^SKY$", "Sky")],
    "Subaru": [(r"^Impreza/Outback Sport$", "Impreza"), (r"^S209$", "WRX")],
    "Suzuki": [(r"^SW$", None)],
    "Toyota": [(r"^Truck/T100$", "T100"), (r"^GR 86$", "GR86"), (r"^GR Supra$", "Supra"), (r"^bZ$", "bZ4X")],
    "Volkswagen": [(r"^Golf/GTI$", "Golf"), (r"^GLI$", "Jetta")],
    "Volvo": [(r"^960.*", "960"), (r"^V70 XC$", "V70")],
    "smart": [],
}
# name of a battery-electric version of a model that also sells with an engine in the same model year
# Model years before 1997, whose EPA records name things differently. Makes that are coachbuilders, conversion
# firms or gray-market importers (hearses, limousines, re-engineered imports) are dropped, and names lose body
# qualifiers and combined names: "Century Wagon" is the Century, "Impala/Caprice" the Impala, "C10 Pickup" the
# C/K 1500. Applied to those years only, after the rules above, so later model years keep their names.
EARLY_YEAR = 1997
EARLY_DROP_MAKES = {
    "ASC Incorporated", "Aurora Cars Ltd", "Autokraft Limited", "Avanti Motor Corporation", "Bertone", "Bill Dovell Motor Car Company",
    "Bitter Gmbh and Co. Kg", "CCC Engineering", "CX Automotive", "Consulier Industries Inc", "Dabryan Coach Builders Inc", "Dacia",
    "Environmental Rsch and Devp Corp", "Evans Automobiles", "Excalibur Autos", "Federal Coach", "General Motors", "Goldacre",
    "Grumman Allied Industries", "Grumman Olson", "Import Foreign Auto Sales Inc", "Import Trade Services", "Isis Imports Ltd",
    "J.K. Motors", "JBA Motorcars, Inc.", "Kenyon Corporation Of America", "Laforza Automobile Inc", "Lambda Control Systems",
    "London Coach Co Inc", "Mcevoy Motors", "PAS Inc - GMC", "PAS, Inc", "Panos", "Panoz Auto-Development", "Panther Car Company Limited",
    "Pininfarina", "Red Shift Ltd.", "Ruf Automobile Gmbh", "Saleen", "TVR Engineering Ltd", "Texas Coach Company",
    "Vixen Motor Company", "Volga Associated Automobile", "Wallace Environmental", "AM General"}
EARLY_MAKE_FIX = {"American Motors Corporation": "AMC"}
EARLY_RENAME = [  # (regex on the cleaned name, replacement; None drops the rows), in order
    (r".*(Coachbuilder|Commercial Chassis|Utility Body|Cab Chassis|Postal|Hearse|Limousine).*", None),
    (r"^Ferrari (.*)$", r"\1"),
    (r"^[CKRV]10( Pickup)?$|^V10 \(K10\)( Pickup)?$|^[CK]1500( Pickup)?$", "C/K 1500"),
    (r"^[CKRV]20( Pickup)?$|^R20 \(C20\)( Pickup)?$|^[CK]2500( Pickup)?$", "C/K 2500"),
    (r"^T10 \(S10\)( Pickup)?$", "S-10"), (r"^S15( Pickup)?$", "S-15"), (r"^Pickup$", None),
    (r"^[DW]100/[DW]150( Pickup)?$|^[DW]150( Pickup)?$", "Ram 1500"), (r"^[DW]250( Pickup)?$", "Ram 2500"),
    (r"^([^/]+?) ?/.*$", r"\1"),                                     # a combined name: its first model
    (r"^(.*\S) \(.*\)$", r"\1"),
    (r"^(.*\S) (Pickup|Estate Wagon|Station Wagon|Wagon|Minivan)$", r"\1"),
]
EV_NAME = {("Ford", "Focus"): "Focus Electric", ("Hyundai", "Kona"): "Kona Electric", ("Hyundai", "Ioniq"): "Ioniq Electric",
           ("Kia", "Niro"): "Niro EV", ("Kia", "Soul"): "Soul EV", ("Toyota", "RAV4"): "RAV4 EV", ("Chevrolet", "Blazer"): "Blazer EV",
           ("Chevrolet", "Equinox"): "Equinox EV", ("Chevrolet", "Silverado"): "Silverado EV", ("GMC", "Sierra"): "Sierra EV",
           ("Chevrolet", "Spark"): "Spark EV", ("Ford", "Ranger"): "Ranger EV", ("Chevrolet", "S-10"): "S-10 Electric",
           ("Honda", "Clarity"): "Clarity Electric", ("smart", "fortwo"): "fortwo electric drive", ("Dodge", "Charger"): "Charger Daytona",
           ("Jeep", "Wagoneer"): "Wagoneer S", ("Porsche", "Macan"): "Macan Electric", ("Maserati", "GranTurismo"): "GranTurismo Folgore",
           ("Maserati", "GranCabrio"): "GranCabrio Folgore", ("Maserati", "Grecale"): "Grecale Folgore", ("Genesis", "GV70"): "Electrified GV70",
           ("Genesis", "G80"): "Electrified G80", ("Volvo", "XC40"): "XC40 Recharge", ("MINI", "Cooper"): "Cooper SE",
           ("Volkswagen", "Golf"): "e-Golf", ("Toyota", "C-HR"): "C-HR", ("Mercedes-Benz", "G-Class"): "G 580 EQ",
           ("Mercedes-Benz", "CLA-Class"): "CLA-Class", ("Lexus", "UX"): "UX 300e", ("Mazda", "MX-30"): "MX-30"}
# Models EPA files under one base name that are sold, insured and recorded as separate models.
SPLIT = [  # (make, base, regex on EPA model, new name)
    ("Land Rover", "Range Rover", r"Evoque", "Range Rover Evoque"), ("Land Rover", "Range Rover", r"Velar", "Range Rover Velar"),
    ("Land Rover", "Range Rover", r"Range Rover Sport", "Range Rover Sport"), ("Land Rover", "Discovery", r"Discovery Sport", "Discovery Sport"),
    ("Land Rover", "Evoque", r".", "Range Rover Evoque"),
    ("Subaru", "Legacy/Outback", r"Outback|incl\. Outback", "Outback"), ("Subaru", "Legacy/Outback", r".", "Legacy"),
    ("Volkswagen", "Golf/GTI", r"GTI", "GTI"), ("Volkswagen", "Golf/GTI", r"Golf R|Golf-R", "Golf R"),
    ("Volkswagen", "Golf/GTI", r"SportWagen|Alltrack", "Golf SportWagen"),
    ("BMW", "M", r"^M(\d)\b(?!\d)", r"M\1"), ("BMW", "M", r"^M(\d)(\d\d)i", r"M\1\2i"), ("BMW", "M", r"^M (Coupe|Roadster)", "Z3 M"),
    ("BMW", "7 Series", r"Alpina", "Alpina B7"), ("Audi", "RS", r"RS ?3", "RS 3"), ("Audi", "RS", r"RS 5", "RS 5"),
    ("Audi", "RS", r"RS 6", "RS 6"), ("Audi", "RS", r"RS 7", "RS 7"),
    ("Chevrolet", "Silverado", r"2500", "Silverado 2500HD"), ("GMC", "Sierra", r"2500", "Sierra 2500HD"),
    ("Chevrolet", "Suburban", r"2500", "Suburban"), ("GMC", "Yukon", r"Yukon XL", "Yukon XL"), ("GMC", "Yukon", r"Denali XL", "Yukon XL"),
    ("Chevrolet", "Silverado", r"Classic", "Silverado"), ("GMC", "Hummer EV", r"Pickup", "Hummer EV Pickup"),
    ("GMC", "Hummer EV", r"SUV", "Hummer EV SUV"), ("Toyota", "Prius", r"Prime", "Prius Prime"),
    ("Lexus", "IS", r"IS F", "IS F"), ("Toyota", "Camry", r"Solara", "Camry Solara"), ("Ram", "1500", r"Classic", "1500 Classic"),
    ("Chrysler", "Pacifica", r".", "Pacifica"), ("Jeep", "Grand Cherokee", r"\bL\b", "Grand Cherokee L"),
    ("Jeep", "Wagoneer", r"Wagoneer L", "Wagoneer L"), ("Jeep", "Grand Wagoneer", r"Grand Wagoneer L", "Grand Wagoneer L"),
    ("Ford", "Bronco", r"Sport", "Bronco Sport"), ("Hyundai", "Kona", r"Kona N", "Kona"),
    ("Hyundai", "Genesis", r"Coupe", "Genesis Coupe"), ("Mitsubishi", "Lancer", r"Evolution", "Lancer Evolution"),
    ("BMW", "M", r"^(X\d) M", r"\1"), ("BMW", "M", r"^1 Series M", "1 Series"), ("BMW", "M", r".", "M3"),
]

VCLASS = [  # (regex on EPA VClass, catalogue class)
    (r"^Minicompact", "Minicompact Car"), (r"^Subcompact", "Subcompact Car"), (r"^Compact", "Compact Car"),
    (r"^Midsize Cars", "Midsize Car"), (r"^Large Cars", "Large Car"), (r"^Two Seaters", "Two-Seater"),
    (r"^Small Station", "Small Wagon"), (r"^Midsize.*Station", "Midsize Wagon"), (r"^Small Sport Utility", "Small SUV"),
    (r"^Standard Sport Utility", "Standard SUV"), (r"^Small Pickup", "Small Pickup"), (r"^Standard Pickup", "Standard Pickup"),
    (r"^Minivan", "Minivan"), (r"^Vans", "Passenger Van"), (r"^Sport Utility", "SUV"), (r"^Special Purpose", "Special Purpose"),
]
BODY_OF_CLASS = {"Small SUV": "SUV", "Standard SUV": "SUV", "SUV": "SUV", "Small Pickup": "Pickup", "Standard Pickup": "Pickup",
                 "Heavy-Duty Pickup": "Pickup", "Minivan": "Minivan", "Passenger Van": "Van", "Small Wagon": "Wagon",
                 "Midsize Wagon": "Wagon"}
FUEL = {"Hybrid": "Hybrid", "Plug-in Hybrid": "Plug-in Hybrid", "EV": "Electric", "Diesel": "Diesel", "FFV": "Flex Fuel",
        "CNG": "Natural Gas", "Bifuel (CNG)": "Natural Gas", "Bifuel (LPG)": "Propane", "FCV": "Hydrogen", "eFCV": "Hydrogen"}
DRIVE = {"Front-Wheel Drive": "FWD", "Rear-Wheel Drive": "RWD", "All-Wheel Drive": "AWD", "4-Wheel or All-Wheel Drive": "4WD",
         "4-Wheel Drive": "4WD", "Part-time 4-Wheel Drive": "4WD", "2-Wheel Drive": "RWD"}

LUXURY_MAKES = {"Acura", "Alfa Romeo", "Aston Martin", "Audi", "Bentley", "BMW", "Bugatti", "Cadillac", "Ferrari", "Fisker", "Genesis",
                "INEOS", "Infiniti", "Jaguar", "Karma", "Koenigsegg", "Lamborghini", "Land Rover", "Lexus", "Lincoln", "Lotus", "Lucid",
                "Maserati", "Maybach", "McLaren", "Mercedes-Benz", "Morgan", "Pagani", "Polestar", "Porsche", "Rivian", "Rolls-Royce",
                "Spyker", "Tesla", "Vector", "Volvo", "Qvale", "Saab", "Hummer"}
SPORTS_MODELS = {("Ford", "Mustang"), ("Ford", "GT"), ("Chevrolet", "Camaro"), ("Chevrolet", "Corvette"), ("Chevrolet", "SS"),
                 ("Dodge", "Challenger"), ("Dodge", "Charger"), ("Dodge", "Viper"), ("Pontiac", "Firebird"),
                 ("Pontiac", "GTO"), ("Pontiac", "Solstice"), ("Saturn", "Sky"), ("Subaru", "BRZ"), ("Subaru", "WRX"), ("Toyota", "86"),
                 ("Toyota", "GR86"), ("Toyota", "Supra"), ("Toyota", "Celica"), ("Toyota", "MR2"), ("Scion", "FR-S"), ("Scion", "tC"),
                 ("Nissan", "350Z"), ("Nissan", "370Z"), ("Nissan", "Z"), ("Nissan", "GT-R"), ("Nissan", "240SX"), ("Mazda", "RX-8"),
                 ("Mazda", "MX-5 Miata"), ("Mazda", "Mazdaspeed3"), ("Mitsubishi", "Eclipse"), ("Mitsubishi", "3000GT"),
                 ("Mitsubishi", "Lancer Evolution"), ("Hyundai", "Tiburon"), ("Hyundai", "Genesis Coupe"), ("Honda", "S2000"),
                 ("Honda", "Prelude"), ("Honda", "CR-Z"), ("Volkswagen", "GTI"), ("Volkswagen", "Golf R"), ("Volkswagen", "R32"),
                 ("Fiat", "124 Spider"), ("Chrysler", "Crossfire"), ("Chrysler", "Prowler"), ("Plymouth", "Prowler"), ("Eagle", "Talon"),
                 ("Acura", "RSX"), ("Acura", "NSX"), ("Kia", "Stinger"), ("Ford", "Thunderbird"), ("Ford", "Probe")}
# make price level relative to a mainstream brand of the same class (ASSUMED; used only where curation gives no price)
MAKE_LEVEL = {"Mitsubishi": 0.85, "Suzuki": 0.85, "Daewoo": 0.75, "Geo": 0.8, "smart": 0.8, "Kandi": 0.6, "Fiat": 0.9, "Scion": 0.9,
              "Saturn": 0.9, "Plymouth": 0.9, "Pontiac": 0.95, "Eagle": 0.95, "Isuzu": 0.95, "Chrysler": 1.05, "Buick": 1.1,
              "MINI": 1.1, "GMC": 1.15, "Saab": 1.3, "Acura": 1.35, "Infiniti": 1.45, "Lexus": 1.5, "Volvo": 1.5, "Alfa Romeo": 1.5,
              "Tesla": 1.4, "Hummer": 1.4, "Fisker": 1.4, "VinFast": 1.3, "CODA": 1.2, "Lordstown": 1.8, "Lincoln": 1.6, "Genesis": 1.6,
              "Audi": 1.6, "Polestar": 1.6, "Cadillac": 1.7, "BMW": 1.7, "Mercedes-Benz": 1.8, "Jaguar": 1.8, "Land Rover": 2.0,
              "INEOS": 2.0, "Rivian": 2.3, "Lucid": 2.6, "Porsche": 2.8, "Maserati": 3.0, "Lotus": 2.8, "Morgan": 3.0, "Qvale": 2.5,
              "Karma": 3.5, "Aston Martin": 5.5, "Spyker": 6.0, "Vector": 5.0, "Bentley": 6.5, "McLaren": 7.0, "Ferrari": 7.5,
              "Lamborghini": 8.0, "Maybach": 9.0, "Rolls-Royce": 10.0, "Bugatti": 60.0, "Pagani": 60.0, "Koenigsegg": 60.0}
CLASS_PRICE = {"Minicompact Car": 24_000, "Subcompact Car": 22_000, "Compact Car": 24_000, "Midsize Car": 28_000, "Large Car": 35_000,
               "Two-Seater": 40_000, "Small Wagon": 25_000, "Midsize Wagon": 32_000, "Small SUV": 29_000, "Standard SUV": 44_000,
               "Small Pickup": 33_000, "Standard Pickup": 44_000, "Heavy-Duty Pickup": 52_000, "Minivan": 39_000, "Passenger Van": 48_000}
CYL_PRICE = {0: 1.0, 2: 0.9, 3: 0.95, 4: 1.0, 5: 1.03, 6: 1.08, 8: 1.2, 10: 1.6, 12: 2.0, 16: 3.0}

CRASH_MAKE = {"GENERAL MOTORS CORPORATION (GMC)": ["GMC"], "RANGE ROVER OF NORTH AMERICA": ["Land Rover"], "ROLLS ROYCE": ["Rolls-Royce"],
              "COOPER": ["MINI"], "FIAT-ABARTH": ["Fiat"], "DODGE": ["Dodge", "Ram"], "MUSTANG": ["Ford"], "BRONCCO": ["Ford"],
              "FIESTA (IMPORTED BY FORD)": ["Ford"], "CHARGER": ["Dodge"], "TRAIL BLAZER": ["Chevrolet"], "FORESTER": ["Subaru"],
              "LANCER": ["Mitsubishi"], "KIA MOTORS CORP": ["Kia"], "SMART": ["smart"]}
CRASH_MAKE_MODEL = {"MUSTANG": "MUSTANG", "BRONCCO": "BRONCO", "FIESTA (IMPORTED BY FORD)": "FIESTA", "CHARGER": "CHARGER",
                    "TRAIL BLAZER": "TRAILBLAZER", "FORESTER": "FORESTER", "LANCER": "LANCER"}
# crash-record model names that do not match a catalogue name by prefix (normalised: upper case, letters and digits only)
CRASH_ALIAS = {"Ford": {"BRONCOBRONCOII": "Bronco", "MAVERICKTRUCK": "Maverick", "F250": "F-250 Super Duty", "F350": "F-350 Super Duty",
                        "SUPERDUTY": "F-250 Super Duty", "ECONOLINEE150": "E-Series Wagon", "CLUBWAGONE350": "E-Series Wagon",
                        "TRANSITCONNECT": "Transit Connect", "MUSTANGMACHE": "Mustang Mach-E", "F150XLT": "F-150", "ETRANSIT": None,
                        "TRANSIT": None, "VAN": None, "CONTOUR": "Contour"},
               "Chevrolet": {"TRAILBLAZER": "Trailblazer", "CK1500": ("C/K 1500", "Silverado"), "C1500": ("C/K 1500", "Silverado"),
                             "CK2500": ("C/K 2500", "Silverado 2500HD"), "CK3500": ("Silverado 3500HD",), "VAN": None,
                             "S10": "S-10", "TRUCK": "Silverado", "BOLT": "Bolt EV", "SILVERADO": "Silverado", "SPORTVAN": "Express"},
               "GMC": {"SAVANNAH": "Savana", "DENALI": "Yukon", "TRUCK": "Sierra", "S15": "Sonoma"},
               "Dodge": {"RAM1500PU": "Ram 1500", "RAM2500PU": "Ram 2500", "RAM3500PU": "Ram 3500", "CARAVAN": "Grand Caravan",
                         "POWERRAM": "Ram 2500", "RAMCHARGER": None},
               "Ram": {"RAM1500PU": "1500", "RAM2500PU": "2500", "RAM3500PU": "3500", "RAMPROMASTER": None},
               "Toyota": {"PRERUNNER": "Tacoma", "T100": "T100", "GRSUPRA": "Supra", "86": "86", "GR86": "GR86", "SOLARA": "Camry Solara"},
               "Mercedes-Benz": {}, "Tesla": {"MODELE": None}, "MINI": {"COOPER": "Cooper"}, "Mazda": {"MAZDA3": "Mazda3", "MAZDA6": "Mazda6",
                                                                                                   "MAZDA2": "Mazda2", "MAZDA5": "Mazda5", "3": "Mazda3", "6": "Mazda6", "MX5": "MX-5 Miata", "MIATA": "MX-5 Miata"},
               "Nissan": {"LEAF": "Leaf"}, "Hummer": {"H2": "H2", "H1": "H1"},
               "Chrysler": {"TOWNCOUNTRY": "Town and Country", "CARAVAN": "Voyager"},
               "Hyundai": {"VELOSTAR": "Veloster", "IONIC": "Ioniq"}, "Mercury": {"MARQUIS": "Grand Marquis"},
               "Land Rover": {"LANDROVERSPORT": "Range Rover Sport", "RANGEROVERPHEV": "Range Rover",
                              "RANGEROVEREVOQUESPORTVELAR": ["Range Rover Evoque", "Range Rover Sport", "Range Rover Velar"]},
               "Lexus": {"300": None, "400": None}, "Audi": {"Q4": "Q4 e-tron", "QUATRRO": None},
               "Acura": {"ZDX": ("MDX",), "RLX": ("RDX",)},
               "Kia": {"K9K900QUORIS": "K900", "CARENSRONDO": "Rondo", "MOHAVEBORREGO": "Borrego", "RIOK2": "Rio"},
               "BMW": {"M3": "M3", "M5": "M5", "M6": "M6"},
               }


UNKNOWN_MODELS = {"", "OTHEREXPLAININNARRATIVE", "UNKNOWN", "NAN", "UNK", "OTHER"}


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def crash_model_key(make: str, key: str) -> str:
    """Crash records often name a model by its engine badge: C300 -> C-Class, ML350 -> ML-Class, 328I -> 3 Series."""
    if make == "Mercedes-Benz":
        m = re.fullmatch(r"(A|B|C|E|S|G|CL|CLA|CLK|CLS|GL|GLA|GLB|GLC|GLE|GLK|GLS|ML|M|R|SL|SLK|SLC)(\d{2,3}).*", key)
        if m:
            return {"M": "MLCLASS"}.get(m.group(1), m.group(1) + "CLASS")
    if make == "BMW":
        m = re.fullmatch(r"([1-8])\d\d[A-Z]*(SERIES)?", key)
        if m:
            return m.group(1) + "SERIES"
    return key


def mode(s: pd.Series):
    m = s.dropna().mode()
    return m.iloc[0] if len(m) else np.nan


def clean_epa(path: Path) -> pd.DataFrame:
    """EPA rows -> one row per (make, model, model year) with class, body, fuel, drive and engine."""
    e = pd.read_csv(zipfile.ZipFile(path).open("vehicles.csv"), low_memory=False)
    e = e[(e.year >= FIRST_YEAR) & (e.year <= LAST_YEAR) & ~e.make.isin(DROP_MAKES)].copy()
    e["make"] = e.make.replace(MAKE_FIX)
    e["name"] = e.baseModel.astype(str).str.strip()
    for make, base, pat, new in SPLIT:
        rx = re.compile(pat)
        for i in e.index[(e.make == make) & (e.baseModel == base) & (e.name == base)]:
            if mt := rx.search(e.at[i, "model"]):
                e.at[i, "name"] = mt.expand(new)
    for make in ["*", *e.make.unique()]:
        for pat, new in RENAME.get(make, []):
            m = e.name.str.fullmatch(pat) & ((e.make == make) if make != "*" else True)
            e.loc[m, "name"] = None if new is None else e.loc[m, "name"].str.replace(pat, new, regex=True).str.strip()
    e = e[e.name.notna() & (e.name != "")]
    early = e.year < EARLY_YEAR
    e = e[~(early & e.make.isin(EARLY_DROP_MAKES))].copy()
    early = e.year < EARLY_YEAR
    e.loc[early, "make"] = e.loc[early, "make"].replace(EARLY_MAKE_FIX)
    for pat, new in EARLY_RENAME:
        m = early & e.name.notna() & e.name.str.fullmatch(pat).fillna(False) & ~e.name.str.startswith("C/K")
        e.loc[m, "name"] = None if new is None else e.loc[m, "name"].str.replace(pat, new, regex=True).str.strip()
    e = e[e.name.notna() & (e.name != "")]
    e = e[~((e.VClass.str.startswith("Vans")) & e.model.str.contains(r"\bVan\b|cargo", case=False, regex=True))]
    # battery-electric versions of a model that also has engines in the same year become their own model
    e["ev"] = e.atvType.eq("EV")
    mixed = e.groupby(["make", "name", "year"]).ev.transform(lambda s: s.any() and not s.all())
    e.loc[mixed & e.ev, "name"] = [EV_NAME.get((mk, nm), f"{nm} EV") for mk, nm in zip(e.make[mixed & e.ev], e.name[mixed & e.ev])]
    e["vclass"] = None
    for pat, cls in VCLASS:
        e.loc[e.vclass.isna() & e.VClass.str.contains(pat, regex=True), "vclass"] = cls
    e["fuel"] = e.atvType.map(FUEL).fillna(pd.Series(np.where(e.fuelType.str.contains("Diesel", na=False), "Diesel", "Gasoline"), index=e.index))
    e["drv"] = e.drive.map(DRIVE)
    low = e.model.str.lower()
    e["body_hint"] = np.select([low.str.contains(r"convertible|cabrio|roadster|spyder|spider|volante|targa|aperta"),
                                low.str.contains(r"coupe|2 ?door|2dr|\b2-door|gran coupe"),
                                low.str.contains(r"hatchback|5-door|3-door|5 door|\bhb\b|liftback|sportback"),
                                low.str.contains(r"wagon|avant|touring|estate|sportwagen|allroad")],
                               ["Convertible", "Coupe", "Hatchback", "Wagon"], default="")
    g = e.groupby(["make", "name", "year"])
    my = g.agg(vclass=("vclass", mode), fuel=("fuel", mode), drive=("drv", mode), cylinders=("cylinders", mode),
               displacement=("displ", "median"), n_configs=("id", "size"),
               body_hint=("body_hint", lambda s: mode(s.replace("", np.nan)) if (s != "").mean() >= 0.5 else "")).reset_index()
    my = my.rename(columns={"name": "model", "year": "model_year"})
    # generic EPA classes (pre-2011 SUVs, special purpose vehicles): use the model's specific class from other years
    specific = my[~my.vclass.isin(["SUV", "Special Purpose"])].groupby(["make", "model"]).vclass.agg(mode)
    gen = my.vclass.isin(["SUV", "Special Purpose"])
    fill = pd.Series([specific.get((a, b), np.nan) for a, b in zip(my.make, my.model)], index=my.index)
    my.loc[gen, "vclass"] = fill[gen]
    left = my.vclass.isna() | my.vclass.isin(["SUV", "Special Purpose"])
    my.loc[left, "vclass"] = np.where(my.displacement[left] >= 4.0, "Standard SUV", "Small SUV")
    my["source"] = "EPA"
    # model years before EPA's data: each model of its first year, carried back with that year's specification
    first = my[my.model_year == EPA_FIRST_YEAR]
    back = [first.assign(model_year=y, source=f"EPA {EPA_FIRST_YEAR}, carried back") for y in range(FIRST_YEAR, EPA_FIRST_YEAR)]
    return pd.concat([my, *back], ignore_index=True)


def add_supplement(my: pd.DataFrame, sup: pd.DataFrame) -> pd.DataFrame:
    rows, have = [], set(zip(my.make, my.model, my.model_year))
    for r in sup.itertuples(index=False):
        for y in range(max(r.first_year, FIRST_YEAR), min(r.last_year, LAST_YEAR) + 1):
            if (r.make, r.model, y) in have:
                continue
            rows.append(dict(make=r.make, model=r.model, model_year=y, vclass=r.vehicle_class, fuel=r.fuel_type, drive=r.drive,
                             cylinders=r.cylinders, displacement=r.displacement, n_configs=1, body_hint="", source="Supplement"))
    return pd.concat([my, pd.DataFrame(rows)], ignore_index=True)


def body_type(r) -> str:
    if r.vclass in BODY_OF_CLASS:
        return BODY_OF_CLASS[r.vclass]
    if r.body_hint:
        return r.body_hint
    return "Coupe" if r.vclass == "Two-Seater" else "Sedan"


# ------------------------------------------------------------------------------------------------ popularity
def crash_counts(path: Path, cat: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Personal-use crash vehicles matched to catalogue model years.

    Returns (matched counts per catalogue row, unmatched 'other' counts per make and model year)."""
    c = pd.read_csv(path, dtype={"make": str, "model": str})
    c = c[c.vehicle_use.isin(PERSONAL_USES) & c.vehicle_year.between(FIRST_YEAR, LAST_YEAR)].copy()
    c["vehicle_year"] = c.vehicle_year.astype(int)
    makes = {m.upper(): [m] for m in cat.make.unique()}
    makes.update(CRASH_MAKE)
    c["makes"] = c.make.map(lambda s: makes.get(str(s).upper()))
    c = c[c.makes.notna()].copy()
    c["model"] = np.where(c.make.isin(CRASH_MAKE_MODEL), c.make.map(CRASH_MAKE_MODEL), c.model)
    c = c.groupby(["make", "model", "vehicle_year"], dropna=False).agg(n=("n", "sum"), makes=("makes", "first")).reset_index()

    avail = {(r.make, r.model, r.model_year): i for i, r in enumerate(cat.itertuples())}
    by_make = {mk: d for mk, d in cat.groupby("make")}
    names = {mk: sorted({(norm(m), m) for m in d.model}, key=lambda t: -len(t[0])) for mk, d in by_make.items()}
    hit = np.zeros(len(cat))
    other = []
    cache: dict = {}
    for r in c.itertuples(index=False):
        key, y = norm(r.model), r.vehicle_year
        found = None
        key = crash_model_key(r.makes[0], key)
        if key and key not in UNKNOWN_MODELS and key != norm(r.make) and key != norm(r.makes[0]):
            ck = (tuple(r.makes), key)
            if ck not in cache:
                cache[ck] = candidates(r.makes, str(r.model), key, names)
            groups = cache[ck]
            if not groups:
                continue        # a model not in the catalogue (commercial van, motorcycle, pre-1997 car): dropped
            # each alternative of an ambiguous name ("OPTIMA / K5") gets an equal part of the records;
            # within one alternative, prefer an exact name, then the longest, sold that year (or one year either side)
            found = []
            for grp in groups:
                for dy in (0, -1, 1):
                    ok = [(mk, nm) for mk, nm in grp if (mk, nm, y + dy) in avail]
                    if ok:
                        exact = [t for t in ok if norm(t[1]) in (key, *[norm(a) for a in str(r.model).split("/")])]
                        found.append(avail[(*(exact or sorted(ok, key=lambda t: -len(norm(t[1]))))[0], y + dy)])
                        break
            if not found:       # a model the make sold, but not that year: a recording error, treated as model unknown
                other.append((r.makes[0], y, r.n))
            for i in set(found):
                hit[i] += r.n / len(set(found))
            continue
        other.append((r.makes[0], y, r.n))
    oth = pd.DataFrame(other, columns=["make", "model_year", "n"]).groupby(["make", "model_year"]).n.sum()
    return hit, oth


def candidates(makes: list[str], raw: str, key: str, names: dict) -> list[list[tuple[str, str]]]:
    """Catalogue models a crash-record model name can mean, as one list per alternative: a combined name such as
    "OPTIMA / K5" or an alias to several models splits its records between them."""
    def lookup(k: str) -> list[list[tuple[str, str]]] | None:
        """Alias targets of every make the record can mean: a list splits the records, a tuple or name is one
        alternative (the model sold in the record's year is taken)."""
        hits = [(mk, CRASH_ALIAS[mk][k]) for mk in makes if k in CRASH_ALIAS.get(mk, {})]
        if not hits:
            return None
        if any(isinstance(t, list) for _, t in hits):
            return [[(mk, x)] for mk, t in hits for x in (t if isinstance(t, list) else [t]) if x]
        grp = [(mk, x) for mk, t in hits for x in (t if isinstance(t, tuple) else (t,)) if x]
        return [grp] if grp else []

    whole = lookup(key)
    if whole is not None:
        return whole
    out = []
    for k in dict.fromkeys(crash_model_key(makes[0], norm(a)) for a in (raw.split("/") if "/" in raw else [raw])):
        found = lookup(k)
        grp = None if found is None else [x for g in found for x in g]
        if grp is None:
            grp = [(mk, nm) for mk in makes for nk, nm in names.get(mk, [])
                   if nk == k or (len(nk) >= 2 and k.startswith(nk)) or (len(k) >= 3 and nk.startswith(k))]
        if grp:
            out.append(grp)
    return out


def popularity(cat: pd.DataFrame, hit: np.ndarray, oth: pd.Series) -> np.ndarray:
    cat = cat.assign(hit=hit)
    named = cat.groupby(["make", "model"]).hit.transform("sum") > 0
    # each make-year's unnamed records go to its models the crash records never name, by sales prior
    cat["alloc"] = 0.0
    for (mk, y), idx in cat[~named].groupby(["make", "model_year"]).groups.items():
        pool = oth.get((mk, y), 0.0)
        if pool <= 0:
            continue
        prior = cat.loc[idx, "sales_prior"]
        all_prior = cat.loc[(cat.make == mk) & (cat.model_year == y), "sales_prior"].sum()
        mk_total = cat.loc[(cat.make == mk) & (cat.model_year == y), "hit"].sum() + pool
        cap = OTHER_SHARE_CAP * prior / all_prior * mk_total
        cat.loc[idx, "alloc"] = np.minimum(pool * prior / prior.sum(), cap)
    cat["count"] = cat.hit + cat.alloc
    tot = cat.groupby("model_year")["count"].transform("sum")
    cat["share"] = cat["count"] / tot
    # smooth shares across neighbouring model years (a model's share changes slowly; recent years are thin)
    years = np.arange(FIRST_YEAR, LAST_YEAR + 1)
    out = np.zeros(len(cat))
    for (mk, md), d in cat.groupby(["make", "model"]):
        s = pd.Series(d.share.to_numpy(), index=d.model_year.to_numpy()).reindex(years)
        n = pd.Series(tot[d.index].to_numpy(), index=d.model_year.to_numpy()).reindex(years).fillna(0)
        for i, y in zip(d.index, d.model_year):
            w = np.exp(-np.abs(years - y) / SMOOTH_TAU) * np.sqrt(n.to_numpy()) * s.notna().to_numpy()
            out[cat.index.get_loc(i)] = np.nansum(w * s.fillna(0).to_numpy()) / max(w.sum(), 1e-12)
    out = np.maximum(out, FLOOR_SHARE * cat.sales_prior.clip(0.05, 5).to_numpy())
    return out / pd.Series(out).groupby(cat.model_year.to_numpy()).transform("sum").to_numpy()


# ------------------------------------------------------------------------------------------------ assembly
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=REPO / "reference/_cache")
    ap.add_argument("--out", type=Path, default=REPO / "reference/vehicle_catalogue.csv")
    a = ap.parse_args()
    cur = pd.read_csv(REPO / "reference/vehicle_curation.csv", comment="#")
    sup = pd.read_csv(REPO / "reference/vehicle_supplement.csv", comment="#")
    cur = cur.merge(sup[["make", "model", "msrp_2024"]], on=["make", "model"], how="outer", suffixes=("", "_sup"))
    cur["msrp_2024"] = cur.msrp_2024.fillna(cur.msrp_2024_sup)

    cat = add_supplement(clean_epa(a.cache / "epa_vehicles.csv.zip"), sup)
    cat["vehicle_class"] = cat.vclass
    cat["body_type"] = [body_type(r) for r in cat.itertuples()]
    # a model's body type is its most common one, so it does not flip between years on a few variants
    cat["body_type"] = cat.groupby(["make", "model"]).body_type.transform(mode)
    cur_i = cur.set_index(["make", "model"])
    key = list(zip(cat.make, cat.model))
    get = lambda col, default: np.array([cur_i[col].get(k, np.nan) if k in cur_i.index else np.nan for k in key], dtype=object) \
        if col in cur_i else np.full(len(cat), default, dtype=object)
    cb, cs, cc = get("body_type", np.nan), get("segment", np.nan), get("vehicle_class", np.nan)
    cat["vehicle_class"] = np.where(pd.notna(cc), cc, cat.vehicle_class)
    cat["body_type"] = np.where(pd.notna(cb), cb, cat.body_type)

    # 2024-equivalent base price: curated, else class x make level x engine (ASSUMED)
    model_class = cat.groupby(["make", "model"]).vehicle_class.transform(mode)
    cyl = cat.groupby(["make", "model"]).cylinders.transform(lambda s: mode(s) if s.notna().any() else 0).fillna(0).astype(int)
    est = model_class.map(CLASS_PRICE).fillna(30_000) * cat.make.map(MAKE_LEVEL).fillna(1.0) \
        * cyl.map(CYL_PRICE).fillna(1.0) * np.where(cat.fuel == "Electric", 1.15, 1.0)
    est = est.groupby([cat.make, cat.model]).transform("median")
    cp = pd.to_numeric(get("msrp_2024", np.nan), errors="coerce")
    cat["msrp_2024"] = np.where(np.isnan(cp), np.round(est, -2), cp).astype(int)
    cat["price_curated"] = ~np.isnan(cp)
    cat["msrp"] = (cat.msrp_2024 * PRICE_GROWTH ** (cat.model_year - 2024)).round(-2).astype(int)

    seg = np.select([cat.fuel.eq("Electric"), model_class.eq("Minivan"), cat.body_type.eq("Pickup"),
                     model_class.eq("Two-Seater") | pd.Series(key, index=cat.index).isin(SPORTS_MODELS),
                     cat.make.isin(LUXURY_MAKES),
                     model_class.isin(["Minicompact Car", "Subcompact Car", "Compact Car", "Small Wagon", "Small SUV"])
                     & (cat.msrp_2024 < 28_000),
                     cat.msrp_2024 < 24_000],
                    ["ev", "minivan", "truck", "sports", "luxury", "economy", "economy"], default="mainstream")
    cat["segment"] = np.where(pd.notna(cs), cs, seg)
    tf = pd.to_numeric(get("theft_factor", np.nan), errors="coerce")
    cat["theft_factor"] = np.where(np.isnan(tf), np.select([cat.segment.eq("ev"), cat.segment.eq("minivan")], [0.3, 0.75], 1.0), tf)
    sp = pd.to_numeric(get("sales_prior", np.nan), errors="coerce")
    default_prior = 40 * (30_000 / cat.msrp_2024) ** 1.5 * np.where(cat.segment.eq("sports"), 0.3, 1.0)
    cat["sales_prior"] = np.where(np.isnan(sp), default_prior, sp)

    cat = cat.sort_values(["make", "model", "model_year"], key=lambda s: s.str.lower() if s.dtype == object else s).reset_index(drop=True)
    hit, oth = crash_counts(a.cache / "chi_crash_vehicles.csv", cat)
    cat["crash_records"] = hit.astype(int)
    cat["popularity"] = popularity(cat, hit, oth)
    cat["model_key"] = cat.groupby(["make", "model"], sort=False).ngroup() + 1
    cat["vehicle_id"] = np.arange(1, len(cat) + 1)
    cat["cylinders"] = np.where(cat.fuel.eq("Electric"), np.nan, cat.cylinders)
    cat["displacement"] = np.where(cat.fuel.eq("Electric"), np.nan, cat.displacement.round(1))
    cols = ["vehicle_id", "model_key", "make", "model", "model_year", "body_type", "vehicle_class", "segment", "fuel", "drive",
            "cylinders", "displacement", "msrp_2024", "msrp", "price_curated", "theft_factor", "crash_records", "popularity", "source"]
    out = cat[cols].rename(columns={"fuel": "fuel_type"})
    out["cylinders"] = out.cylinders.astype("Int64")
    out["popularity"] = out.popularity.round(9)
    out.to_csv(a.out, index=False)
    w = out.groupby("model_year").popularity.transform("sum")
    print(f"wrote {a.out}: {len(out):,} model years of {out.model_key.nunique():,} models from {out.make.nunique()} makes")
    print(f"crash records matched: {int(hit.sum()):,}; unnamed (other/unknown model): {int(oth.sum()):,}")


if __name__ == "__main__":
    main()
