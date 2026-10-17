"""Build the UniPlan parser final exam (English only). Run: python3 -I build_exam.py

All sentences and answers are synthetic, written by Claude as an independent exam writer.
They are not real student data.
"""
import collections
import csv
import random
import sys

OUT = "/private/tmp/claude-501/-Users-handongrui-Desktop-ENGG2112/4ea07490-ad49-4f06-bed5-31e6c5544e5f/scratchpad/exam/exam_parse.csv"

BT, MD, MH, LU, IP, FD, LW, EL, OT = ("blocked_time", "max_days", "max_daily_hours", "lunch", "in_person_only",
                                      "prefer_fewer_days", "prefer_less_waiting", "prefer_no_early_late", "other")
W = None  # clause = whole sentence
DATA = {}


def s(key, sentence, *clauses):
    assert key not in DATA, key
    DATA[key] = (sentence, clauses)


def c(text, label, val=None, note=""):
    return (text, label, val, note)


DEF_LUNCH = "11:30-14:00 30"
WK = "Mon-Fri"

# ---------------------------------------------------------------- set A
s("E1", "I work at Woolies every Friday so I can't do anything that day",
  c(W, BT, "Fri all", "back-reference 'that day' stays in the clause"))
s("E2", "no 9ams please, and I'd like to be finished by 4 if possible",
  c("no 9ams please", BT, WK + " 0:00-10:00", "a 9am class runs to 10"),
  c("I'd like to be finished by 4 if possible", EL, "9:00-16:00", "hedged clock time, no day, no commitment"))
s("E3", "Max 3 days on campus a week, my commute is like 90 mins each way",
  c(W, MD, 3, "commute minutes are the reason, kept with the request"))
s("E4", "Im not a morning person at all lol", c(W, EL))
s("E5", "I pick up my daughter from daycare at 3:30 so nothing after that",
  c(W, BT, WK + " 15:30-24:00"))
s("E6", "can u keep tuesday and thursday arvos free, I coach under 12s soccer",
  c(W, BT, "Tue,Thu 12:00-18:00", "reason kept with the request; '12s' is an age group"))
s("E7", "Online classes are fine by me, actually I'd prefer them", c(W, OT, note="wants online classes"))
s("E8", "Face to face only pls, I can't focus on Zoom", c(W, IP))
s("E9", "I don't want long gaps between classes, I'd rather just go home", c(W, LW))
s("E10", "Can I have all my classes on as few days as possible", c(W, FD))
s("E11", "Need a proper lunch break, at least 45 min, sometime between 12 and 2",
  c(W, LU, "12:00-14:00 45"))
s("E12", "No more than 5 hours of class a day or my brain melts", c(W, MH, ("c", 5)))
s("E13", "I'm at uni anyway on Wednesdays so stick as many classes there as you like",
  c(W, OT, note="only says a day is good; no request"))
s("E14", "I go to Jumu'ah at the mosque on Fridays from 1 to 2, so keep that hour clear",
  c(W, BT, "Fri 13:00-14:00"))
s("E15", "two days a week ideally, three at a push", c(W, MD, 3, "real limit is the larger number"))
s("E16", "Not before 10am on Mondays and not after 3pm on Fridays",
  c("Not before 10am on Mondays", BT, "Mon 0:00-10:00"),
  c("not after 3pm on Fridays", BT, "Fri 15:00-24:00"))
s("E17", "honestly whatever works, I'm easy", c(W, OT))
s("E18", "Theres a 40 min walk from Redfern so 8am classes are a no go",
  c(W, BT, WK + " 0:00-9:00", "an 8am class runs to 9; walk minutes are a distractor"))
s("E19", "I'd like my tute with Priya and Josh if that's possible", c(W, OT))
s("E20", "I have physio every Tuesday morning and I'd rather keep lunchtimes free to eat",
  c("I have physio every Tuesday morning", BT, "Tue 0:00-10:00"),
  c("I'd rather keep lunchtimes free to eat", LU, DEF_LUNCH, "eating, no clock time"))
s("E21", "I'm a carer for my dad so I need to be home by 5 every day",
  c(W, BT, WK + " 17:00-24:00", "home by 5 = must leave by 5"))
s("E22", "no classes on mondays wednesdays or fridays, i work those days", c(W, BT, "Mon,Wed,Fri all"))
s("E23", "only tues and thurs work for me", c(W, BT, "Mon,Wed,Fri all", "only these days: block the other weekdays"))
s("E24", "I don't mind early starts, 8am is totally fine",
  c(W, OT, note="likes early starts; a clock time that is fine is not a block"))
s("E25", "Please don't give me 6pm classes, the trains after that are sketchy",
  c(W, BT, WK + " 18:00-24:00", "6pm classes"))
s("E26", "I'd prefer to start at 11 or later", c(W, EL, "11:00-18:00"))
s("E27", "Keep my mornings free if you can, I've got swim squad",
  c(W, BT, WK + " 0:00-10:00", "part-of-day word + request; the hedge does not apply"))
s("E28", "I'd really like back to back classes so I'm not hanging around", c(W, LW))
s("E29", "max 6 hrs on campus per day, I get migraines", c(W, MH, ("s", 6)))
s("E30", "No online lectures. No classes before 9 either.",
  c("No online lectures", IP),
  c("No classes before 9 either", BT, WK + " 0:00-9:00"))
s("E31", "I'd rather not come in on Fridays", c(W, BT, "Fri all", "a hedge does not soften a weekday"))
s("E32", "I'm doing a second degree at TAFE on Monday nights", c(W, BT, "Mon 18:00-24:00"))
s("E33", "lunch 12-1 non negotiable", c(W, LU, "12:00-13:00 60"))
s("E34", "Can I get everything done in 3 days? Thursday and Friday I'm at my internship",
  c("Can I get everything done in 3 days", MD, 3),
  c("Thursday and Friday I'm at my internship", BT, "Thu,Fri all"))
s("E35", "I don't want to be at uni longer than 8 hours a day, including breaks", c(W, MH, ("s", 8)))
s("E36", "Can my classes be squeezed into fewer days? and no big gaps pls",
  c("Can my classes be squeezed into fewer days", FD),
  c("no big gaps pls", LW))
s("E37", "I'm a mum of two (4 and 7) and I drop them at school at 8:45",
  c(W, BT, WK + " 0:00-9:45", "one morning clock -> 0:00-(X+1); the kids' ages are distractors"))
s("E38", "I hate 8ams with a passion",
  c(W, BT, WK + " 0:00-9:00", "a clock time is blocked_time even when said as a feeling (rule 4 before rule 6)"))
s("E39", "Wednesdays I'm free all day btw", c(W, OT, note="only says a day is free"))
s("E40", "I had a 3 hour gap last sem and it sucked, pls avoid that",
  c(W, LW, note="3 hours is a gap length, not hours per day"))
s("E41", "No classes after 7pm, I do Uber Eats", c(W, BT, WK + " 19:00-24:00"))
s("E42", "Ideally done by 2 most days", c(W, EL, "9:00-14:00", "hedged clock; 2 without am/pm = 14:00"))
s("E43", "During Ramadan I'd rather avoid evening classes",
  c(W, BT, WK + " 18:00-24:00", "part-of-day word + request; the hedge does not apply"))
s("E44", "Mon Wed Fri is all I can do", c(W, BT, "Tue,Thu all", "only these days"))
s("E45", "I just want a compact week, like not coming in every single day", c(W, FD))
s("E46", "please put me in the in-person tutes, not the online ones", c(W, IP))
s("E47", "I want to grab lunch with my friends between 1 and 2 every day",
  c(W, LU, "13:00-14:00 60", "eating comes first (rule 1); friends do not make it other"))
s("E48", "Footy training Tues/Thurs 5:30 onwards and games are Saturdays",
  c("Footy training Tues/Thurs 5:30 onwards", BT, "Tue,Thu 17:30-24:00", "5:30 without am/pm = 17:30"),
  c("games are Saturdays", BT, "Sat all"))
s("E49", "I can do 4 days max but 3 would be heaps better", c(W, MD, 4, "real limit is the larger number"))
s("E50", "Not too early please, I live out in Penrith", c(W, EL, note="vague 'too early'"))
s("E51", "I get the 7:10 train and it gets into Central at 8:25, so I can't make anything before 9",
  c(W, BT, WK + " 0:00-9:00", "train times are the reason; the request is 'before 9'"))
s("E52", "I need 30 mins to eat, don't care when", c(W, LU, DEF_LUNCH))
s("E53", "No more than 4 hours of classes on any day and no more than 3 days a week",
  c("No more than 4 hours of classes on any day", MH, ("c", 4)),
  c("no more than 3 days a week", MD, 3))
s("E54", "the less I have to come in the better tbh", c(W, FD))
s("E55", "I want Dr Chen's lecture stream for ENGG2112", c(W, OT, note="lecturer"))
s("E56", "I have chemo every second Thursday", c(W, BT, "Thu all", "alternate weeks cannot be expressed: whole day"))
s("E57", "I'd like to keep my Mondays free for my part time job and nothing past 5pm on other days",
  c("I'd like to keep my Mondays free for my part time job", BT, "Mon all"),
  c("nothing past 5pm on other days", BT, "Tue-Fri 17:00-24:00", "'other days' = the other weekdays"))
s("E58", "ideally classes between 10 and 3", c(W, EL, "10:00-15:00"))
s("E59", "I play in a band and we rehearse Wednesday 7-10pm", c(W, BT, "Wed 19:00-22:00"))
s("E60", "I don't care about gaps, I study in the library between classes anyway",
  c(W, OT, note="gaps are fine; no request"))
s("E61", "I'm international and my visa lets me work 48 hours a fortnight so I need my classes squished into 3 days",
  c(W, MD, 3, "48 hours a fortnight is a distractor"))
s("E62", "No early mornings and no late nights",
  c("No early mornings", EL, note="modified part-of-day"),
  c("no late nights", EL, note="modified part-of-day"))
s("E63", "Please no evening classes", c(W, BT, WK + " 18:00-24:00"))
s("E64", "i need to be outta there by 3 on tuesdays to get to my sons swimming", c(W, BT, "Tue 15:00-24:00"))
s("E65", "I'd like half an hour for lunch somewhere between 12 and 1:30", c(W, LU, "12:00-13:30 30"))
s("E66", "I'm happy to start early but I want to finish by 2",
  c("I'm happy to start early", OT),
  c("I want to finish by 2", BT, WK + " 14:00-24:00", "'want' is not a hedge"))
s("E67", "Monday classes are a nah from me", c(W, BT, "Mon all"))
s("E68", "Could you make sure I'm not stuck on campus for more than 7 hours, first class to last",
  c(W, MH, ("s", 7)))
s("E69", "i reckon 2 days a week is plenty", c(W, MD, 2))
s("E70", "I volunteer at the hospital Thursday mornings from 8 till 12",
  c(W, BT, "Thu 8:00-12:00", "explicit times override the 'morning' default"))
s("E71", "No 8ams no 6pms",
  c("No 8ams", BT, WK + " 0:00-9:00"),
  c("no 6pms", BT, WK + " 18:00-24:00"))
s("E72", "I want all my classes in person, I learn way better that way", c(W, IP))
s("E73", "Gaps longer than an hour between classes are the worst", c(W, LW, note="'an hour' is a gap length"))
s("E74", "I don't mind which days as long as there are only 3 of them", c(W, MD, 3))
s("E75", "My mental health is better when I'm not rushing so I'd like an actual lunch break", c(W, LU, DEF_LUNCH))
s("E76", "I can only come in after 11 on Tuesdays and Thursdays because I drive my grandma to dialysis",
  c(W, BT, "Tue,Thu 0:00-11:00"))
s("E77", "Not Friday arvo pls, I've got netball", c(W, BT, "Fri 12:00-18:00"))
s("E78", "I'm a night owl, later classes suit me way better", c(W, EL, note="feeling, no clock time"))
s("E79", "I need Wednesday off for my dad's medical appointments, otherwise anything goes",
  c("I need Wednesday off for my dad's medical appointments", BT, "Wed all"),
  c("otherwise anything goes", OT))
s("E80", "I'd prefer not to have anything before 10 but Mondays I literally can't before 12",
  c("I'd prefer not to have anything before 10", EL, "10:00-18:00"),
  c("Mondays I literally can't before 12", BT, "Mon 0:00-12:00"))
s("E81", "no zoom pls", c(W, IP))
s("E82", "keep classes close together so I'm not waiting round", c(W, LW))
s("E83", "Ideally 3 days or fewer", c(W, MD, 3))
s("E84", "Shifts at Maccas Sat Sun and Tuesday night", c(W, BT, "Tue 18:00-24:00; Sat,Sun all"))
s("E85", "I'm 19, first year, living on res, pretty flexible", c(W, OT))
s("E86", "I need to leave by 2:30 on Mon and Wed for school pickup", c(W, BT, "Mon,Wed 14:30-24:00"))
s("E87", "if possible no classes after 4", c(W, EL, "9:00-16:00", "hedged clock, no day"))
s("E88", "no classes after 4 on Thursdays if possible",
  c(W, BT, "Thu 16:00-24:00", "weekday named, so the hedge does not apply"))
s("E89", "Lunch has to be at least an hour, I'm diabetic and need to eat properly", c(W, LU, "11:30-14:00 60"))
s("E90", "I'm fine with online lectures but tutorials need to be in person",
  c("I'm fine with online lectures", OT),
  c("tutorials need to be in person", IP))
s("E91", "Can I have at most 5 hrs of class per day and get home before dark",
  c("Can I have at most 5 hrs of class per day", MH, ("c", 5)),
  c("get home before dark", EL, note="vague; no clock time or part-of-day word"))
s("E92", "I have church on Wednesday evenings and all day Sunday", c(W, BT, "Wed 18:00-24:00; Sun all"))
s("E93", "Pls dont make me come in 5 days a week", c(W, MD, 4, "not 5 days = at most 4"))
s("E94", "No more than 2 days, I've got a newborn", c(W, MD, 2))
s("E95", "My shifts are 10am to 2pm on Mondays and 5 to 9pm Thursdays", c(W, BT, "Mon 10:00-14:00; Thu 17:00-21:00"))
s("E96", "breaks between classes shouldnt be more than like 30 mins", c(W, LW, note="30 mins is a gap length"))
s("E97", "I'm a uni rower, we're on the water till 7:30 every morning so nothing before 9",
  c(W, BT, WK + " 0:00-9:00"))
s("E98", "I'm hard of hearing so online classes with captions are actually easier for me",
  c(W, OT, note="wants online classes"))
s("E99", "I have a casual job and the roster changes every week so I can't really say", c(W, OT))
s("E100", "No more than three days on campus and ideally nothing on Monday",
  c("No more than three days on campus", MD, 3),
  c("ideally nothing on Monday", BT, "Mon all", "weekday: hedge does not apply"))
s("E101", "I work every arvo from 1 so no classes after 1", c(W, BT, WK + " 13:00-24:00"))
s("E102", "Can you keep the 12 to 1 slot free for lunch", c(W, LU, "12:00-13:00 60"))
s("E103", "Can you keep 12 to 1 free on Fridays for prayers", c(W, BT, "Fri 12:00-13:00", "prayer, not eating"))
s("E104", "I want to finish my degree in 3 years so I'm doing 5 units this sem", c(W, OT))
s("E105", "I don't want to trek out to the Cumberland campus", c(W, OT, note="location"))
s("E106", "Tuesdays are a write-off because of my internship, and keep it to 6 hours of classes max the other days",
  c("Tuesdays are a write-off because of my internship", BT, "Tue all"),
  c("keep it to 6 hours of classes max the other days", MH, ("c", 6)))
s("E107", "Evenings are out, I look after my little brother", c(W, BT, WK + " 18:00-24:00"))
s("E108", "nothing after 5 and no 2hr breaks pls",
  c("nothing after 5", BT, WK + " 17:00-24:00"),
  c("no 2hr breaks pls", LW, note="2hr is a gap length"))
s("E109", "Could I please have Mondays and Fridays off", c(W, BT, "Mon,Fri all"))
s("E110", "Thursdays I have uni sport from 2pm", c(W, BT, "Thu 14:00-24:00"))
s("E111", "pls no more than 4 days, I work the rest", c(W, MD, 4))
s("E112", "Classes one after the other please, I hate sitting around", c(W, LW))
s("E113", "i'm an early bird so mornings are actually great for me",
  c(W, OT, note="likes mornings; no request"))
s("E114", "Weeknights after 6 are no good, I do TAFE", c(W, BT, WK + " 18:00-24:00"))
s("E115", "I'd rather not spend more than 9 hours at uni in a day", c(W, MH, ("s", 9)))
s("E116", "Two days on campus, maybe three if it has to be", c(W, MD, 3))
s("E117", "I have a standing therapy appointment Wednesdays at 4pm",
  c(W, BT, "Wed 16:00-24:00", "one afternoon clock -> X-24:00"))
s("E118", "No classes before 10 except Wednesday when I can do 9",
  c(W, BT, "Mon,Tue,Thu,Fri 0:00-10:00; Wed 0:00-9:00"))
s("E119", "No online stuff, no 8:30 starts, and keep Friday free",
  c("No online stuff", IP),
  c("no 8:30 starts", BT, WK + " 0:00-9:30", "a class starting at 8:30 runs to 9:30"),
  c("keep Friday free", BT, "Fri all"))
s("E120", "I want the same tute as my flatmate so I actually know someone", c(W, OT))
s("E121", "I hate waiting around for 3 hours between classes", c(W, LW))
s("E122", "Weekly hockey Thursday evening and a gym class at 7am Tuesdays",
  c("Weekly hockey Thursday evening", BT, "Thu 18:00-24:00"),
  c("a gym class at 7am Tuesdays", BT, "Tue 0:00-8:00", "one morning clock -> 0:00-(X+1)"))
s("E123", "mornings and arvos r fine, just not fridays",
  c("mornings and arvos r fine", OT),
  c("just not fridays", BT, "Fri all"))
s("E124", "I need to eat lunch at a normal time, like between 12 and 1", c(W, LU, "12:00-13:00 60"))
s("E125", "my anxiety is worse on long days so cap it at 6 hours on campus and give me a lunch break",
  c("my anxiety is worse on long days so cap it at 6 hours on campus", MH, ("s", 6)),
  c("give me a lunch break", LU, DEF_LUNCH))
s("E126", "I'm a single dad, school drop off is 8:30 and pick up is 3",
  c("I'm a single dad, school drop off is 8:30", BT, WK + " 0:00-9:30", "one morning clock -> 0:00-(X+1)"),
  c("pick up is 3", BT, WK + " 15:00-24:00"))
s("E127", "Prefer not to start before 9:30", c(W, EL, "9:30-18:00"))
s("E128", "Kinda want Friday off ngl", c(W, BT, "Fri all"))
s("E129", "Online lectures yes, online tutes no",
  c("Online lectures yes", OT),
  c("online tutes no", IP))
s("E130", "I want to minimise the days I travel in, petrol is so expensive", c(W, FD))
s("E131", "I'd prefer a 3 day week", c(W, MD, 3))
s("E132", "I teach swimming lessons Monday and Wednesday 3:30 to 6:30", c(W, BT, "Mon,Wed 15:30-18:30"))
s("E133", "I've got driving lessons Friday arvo and I see my psych Tuesday at 10am",
  c("I've got driving lessons Friday arvo", BT, "Fri 12:00-18:00"),
  c("I see my psych Tuesday at 10am", BT, "Tue 0:00-11:00", "one morning clock -> 0:00-(X+1)"))
s("E134", "Not a fan of gaps, not a fan of 8ams either",
  c("Not a fan of gaps", LW),
  c("not a fan of 8ams either", BT, WK + " 0:00-9:00", "clock time -> blocked_time even as a feeling"))
s("E135", "Every second Monday I have a custody handover", c(W, BT, "Mon all", "alternate weeks -> whole day"))
s("E136", "keep my days short pls, like 4 hours of class max", c(W, MH, ("c", 4)))
s("E137", "Uni is 2 hours away by train so I'd prefer to come in less often", c(W, FD, note="2 hours is the commute"))
s("E138", "I have an exam clash in week 8, can u sort it", c(W, OT, note="exams"))
s("E139", "I'd like to avoid 6 to 8pm, I'm at cricket",
  c(W, BT, WK + " 18:00-20:00", "hedge + clock but with a commitment -> blocked_time"))
s("E140", "Long breaks are actually good for me, I need time to rest and pray",
  c(W, OT, note="wants gaps; the opposite of less waiting"))
s("E141", "nothing before 11 on mon tue wed", c(W, BT, "Mon-Wed 0:00-11:00"))
s("E142", "I work 9 to 5 on Thursdays at my internship", c(W, BT, "Thu 9:00-17:00"))
s("E143", "I can only get there after 10, and Wednesdays are a no",
  c("I can only get there after 10", BT, WK + " 0:00-10:00"),
  c("Wednesdays are a no", BT, "Wed all"))
s("E144", "Every day I need to be home by 6:30 to cook for my kids",
  c(W, BT, WK + " 18:30-24:00", "dinner, not lunch"))
s("E145", "I want at least 40 mins for lunch between 11:30 and 1:30", c(W, LU, "11:30-13:30 40"))
s("E146", "Don't mind gaps, do mind 8am classes",
  c("Don't mind gaps", OT),
  c("do mind 8am classes", BT, WK + " 0:00-9:00"))
s("E147", "I work at a pub Thursday Friday and Saturday nights", c(W, BT, "Thu-Sat 18:00-24:00"))
s("E148", "Keep me under 20 contact hours a week", c(W, OT, note="hours per week, not per day"))
s("E149", "I'd like to be finished by 3 on Fridays so I can get the train home to Newcastle",
  c(W, BT, "Fri 15:00-24:00"))
s("E150", "early classes are a struggle with my meds", c(W, EL))
s("E151", "I work Mon and Thu, I want max 4 hrs of class a day, and pls no gaps longer than an hour",
  c("I work Mon and Thu", BT, "Mon,Thu all"),
  c("I want max 4 hrs of class a day", MH, ("c", 4)),
  c("pls no gaps longer than an hour", LW))
s("E152", "3 days max, nothing before 10, lunch break needed, in person only",
  c("3 days max", MD, 3),
  c("nothing before 10", BT, WK + " 0:00-10:00"),
  c("lunch break needed", LU, DEF_LUNCH),
  c("in person only", IP))
s("E153", "Not a morning person so ideally nothing before 11, and I'd like my classes packed into as few days as possible",
  c("Not a morning person so ideally nothing before 11", EL, "11:00-18:00", "feeling + hedged clock: prefer_hours from the clock"),
  c("I'd like my classes packed into as few days as possible", FD))
s("E154", "I've got a part time job at JB Hi-Fi on Wednesday and Saturday, I'd rather not be on campus more than 8 hours a day, and I'm happy with any lecturer",
  c("I've got a part time job at JB Hi-Fi on Wednesday and Saturday", BT, "Wed,Sat all"),
  c("I'd rather not be on campus more than 8 hours a day", MH, ("s", 8)),
  c("I'm happy with any lecturer", OT))
s("E155", "Fewer days is my top priority but I also don't want to sit around between classes",
  c("Fewer days is my top priority", FD),
  c("I also don't want to sit around between classes", LW))
s("E156", "max 5 hrs on campus a day and lunch from 12 to 12:30",
  c("max 5 hrs on campus a day", MH, ("s", 5)),
  c("lunch from 12 to 12:30", LU, "12:00-12:30 30"))
s("E157", "I look after my mum on Tuesdays, I can't do anything past 4 on the other days, and only in-person classes please",
  c("I look after my mum on Tuesdays", BT, "Tue all"),
  c("I can't do anything past 4 on the other days", BT, "Mon,Wed-Fri 16:00-24:00"),
  c("only in-person classes please", IP))
s("E158", "early starts kill me, gaps kill me, Friday classes kill me",
  c("early starts kill me", EL),
  c("gaps kill me", LW),
  c("Friday classes kill me", BT, "Fri all", "named weekday -> blocked_time even as a feeling"))
s("E159", "I'd like two days a week, no evening classes, and I want to be in the same lab group as my mate Tom",
  c("I'd like two days a week", MD, 2),
  c("no evening classes", BT, WK + " 18:00-24:00"),
  c("I want to be in the same lab group as my mate Tom", OT))
s("E160", "Basically I need Thursdays free for my research assistant job and nothing after 5 on the other days",
  c("Basically I need Thursdays free for my research assistant job", BT, "Thu all"),
  c("nothing after 5 on the other days", BT, "Mon-Wed,Fri 17:00-24:00"))
s("E161", "no classes before 10 no classes after 4 no classes on friday",
  c("no classes before 10", BT, WK + " 0:00-10:00"),
  c("no classes after 4", BT, WK + " 16:00-24:00"),
  c("no classes on friday", BT, "Fri all"))
s("E162", "Hi! I'm a mature age student with a full time job, so I can only do Monday and Wednesday evenings, thanks",
  c("I'm a mature age student with a full time job, so I can only do Monday and Wednesday evenings", BT,
    "Mon,Wed 0:00-18:00; Tue,Thu,Fri all", "only these times: everything else on weekdays is blocked; greetings dropped"))
s("E163", "Thanks heaps! Max 3 days and keep my lunch free",
  c("Max 3 days", MD, 3),
  c("keep my lunch free", LU, DEF_LUNCH))
s("E164", "Honestly I don't care about the days, just don't put me in anything that starts before 9:30 and give me an hour for lunch",
  c("Honestly I don't care about the days", OT),
  c("just don't put me in anything that starts before 9:30", BT, WK + " 0:00-9:30"),
  c("give me an hour for lunch", LU, "11:30-14:00 60"))
s("E165", "I'm on a sports scholarship, training is 6-8am and 4-6pm every weekday, and I need lunch",
  c("I'm on a sports scholarship, training is 6-8am and 4-6pm every weekday", BT, WK + " 6:00-8:00; " + WK + " 16:00-18:00"),
  c("I need lunch", LU, DEF_LUNCH))
s("E166", "No Mondays (work), no Wednesdays (uni netball), and nothing after 6 any day",
  c("No Mondays (work)", BT, "Mon all"),
  c("no Wednesdays (uni netball)", BT, "Wed all"),
  c("nothing after 6 any day", BT, WK + " 18:00-24:00"))
s("E167", "I'd like to cut down on how many days I come in, and when I do come in, no huge breaks",
  c("I'd like to cut down on how many days I come in", FD),
  c("when I do come in, no huge breaks", LW))
s("E168", "At most 6 hours of class a day, at most 9 hours on campus, and ideally start after 10",
  c("At most 6 hours of class a day", MH, ("c", 6)),
  c("at most 9 hours on campus", MH, ("s", 9)),
  c("ideally start after 10", EL, "10:00-18:00"))
s("E169", "my bf and I want the same tutes, we both work Fridays",
  c("my bf and I want the same tutes", OT),
  c("we both work Fridays", BT, "Fri all"))
s("E170", "I cant be there tuesday at all and thursday i have to leave by 1",
  c("I cant be there tuesday at all", BT, "Tue all"),
  c("thursday i have to leave by 1", BT, "Thu 13:00-24:00"))
s("E171", "cant do wensdays or thrusday mornings sry", c(W, BT, "Wed all; Thu 0:00-10:00", "typos in day names"))
s("E172", "no classes befor 10 on tuesdys", c(W, BT, "Tue 0:00-10:00"))
s("E173", "i need a lunch brake around 12-1", c(W, LU, "12:00-13:00 60", "typo 'brake'"))
s("E174", "id rather start after 10am if thats possible", c(W, EL, "10:00-18:00"))
s("E175", "my job is mon wed n fri from 4 so no clases after 4 those days", c(W, BT, "Mon,Wed,Fri 16:00-24:00"))
s("E176", "ok so basically i work at a cafe on tuesday and thursday mornings until 11 and i also have a toddler so i need to be home by 5 and i dont want more than 3 days",
  c("ok so basically i work at a cafe on tuesday and thursday mornings until 11", BT, "Tue,Thu 0:00-11:00"),
  c("i also have a toddler so i need to be home by 5", BT, WK + " 17:00-24:00"),
  c("i dont want more than 3 days", MD, 3))
s("E177", "Look I'm doing 4 units while working 30 hrs a week so I need everything in 2 days max and preferably no gaps",
  c("Look I'm doing 4 units while working 30 hrs a week so I need everything in 2 days max", MD, 2,
    "4 units and 30 hrs a week are distractors"),
  c("preferably no gaps", LW))
s("E178", "Kind of a weird one but I'm a volunteer firefighter and get called out randomly, so no preference really",
  c(W, OT))
s("E180", "If I could avoid late arvo classes that'd be great", c(W, EL, note="'late arvo' is a modified part-of-day"))
s("E181", "Nothing too late in the day please, I'm on the Central Coast", c(W, EL, note="vague 'too late'"))
s("E182", "I'd like to come in as little as possible, and no Monday classes since I work Mondays",
  c("I'd like to come in as little as possible", FD),
  c("no Monday classes since I work Mondays", BT, "Mon all"))
s("E183", "Condense my week pls, and no lectures after 5",
  c("Condense my week pls", FD),
  c("no lectures after 5", BT, WK + " 17:00-24:00"))
s("E184", "Not every day pls, I have a 3 year old at home",
  c(W, FD, note="'not every day' has no count; 3 year old is an age"))

# ---------------------------------------------------------------- set B
s("N1", "I've got chronic fatigue so I can't be on campus more than 6 hours a day", c(W, MH, ("s", 6)))
s("N2", "Class hours per day: 4 max. Days per week: 3 max. Lunch: yes pls.",
  c("Class hours per day: 4 max", MH, ("c", 4)),
  c("Days per week: 3 max", MD, 3),
  c("Lunch: yes pls", LU, DEF_LUNCH))
s("N3", "I want to keep my classes to 3.5 hours a day tops, I'm also a TA", c(W, MH, ("c", 3.5)))
s("N4", "first class to last class shouldn't be longer than 8 hrs, and I need a 30 min feed somewhere in the middle",
  c("first class to last class shouldn't be longer than 8 hrs", MH, ("s", 8)),
  c("I need a 30 min feed somewhere in the middle", LU, DEF_LUNCH, "'feed' = a meal; no clock time"))
s("N5", "I'd like to not be at uni more than 10 hours on any day, it's a long trip home", c(W, MH, ("s", 10)))
s("N6", "Keep it to five hours of class a day and don't make me come in Monday",
  c("Keep it to five hours of class a day", MH, ("c", 5)),
  c("don't make me come in Monday", BT, "Mon all"))
s("N7", "Nothing longer than a 7 hour day on campus, nothing before 9:30, and Thursdays off",
  c("Nothing longer than a 7 hour day on campus", MH, ("s", 7)),
  c("nothing before 9:30", BT, WK + " 0:00-9:30"),
  c("Thursdays off", BT, "Thu all"))
s("N8", "max 3 hrs of lectures and tutes per day pls my attention span is cooked", c(W, MH, ("c", 3)))
s("N9", "I don't wanna do more than 6 hours of class on any one day, but I don't mind if I'm on campus till late",
  c("I don't wanna do more than 6 hours of class on any one day", MH, ("c", 6)),
  c("I don't mind if I'm on campus till late", OT, note="fine with late; no request"))
s("N10", "My days on campus can't go longer than 9 hours because of my carer duties at home", c(W, MH, ("s", 9)))
s("N11", "I'm partially sighted and screens wreck my eyes so no more than 4 hours of class a day and nothing online",
  c("I'm partially sighted and screens wreck my eyes so no more than 4 hours of class a day", MH, ("c", 4)),
  c("nothing online", IP))
s("N12", "Short days please, like 5 hours on campus max, and back to back where possible",
  c("Short days please, like 5 hours on campus max", MH, ("s", 5)),
  c("back to back where possible", LW))
s("N13", "I'm doing a 20 hour a week internship so I need classes capped at 4 hours a day",
  c(W, MH, ("c", 4), "20 hours a week is a distractor"))
s("N14", "6 hours of class in a day is the most I can handle", c(W, MH, ("c", 6)))
s("N15", "I'd like my classes to be no more than 5 hrs per day and my time at uni no more than 8",
  c("I'd like my classes to be no more than 5 hrs per day", MH, ("c", 5)),
  c("my time at uni no more than 8", MH, ("s", 8)))
s("N16", "Can you keep every uni day to 4 hours of class, I've got two jobs", c(W, MH, ("c", 4)))
s("N17", "I'd rather do a few long days than lots of short ones", c(W, FD))
s("N18", "I just want to rock up as few times a week as I can", c(W, FD))
s("N19", "pack my classes into the smallest number of days possible, gaps are fine",
  c("pack my classes into the smallest number of days possible", FD),
  c("gaps are fine", OT))
s("N20", "Not coming in every day would be a dream, and if I have to be in, keep the classes back to back",
  c("Not coming in every day would be a dream", FD),
  c("if I have to be in, keep the classes back to back", LW))
s("N21", "Prefer fewer campus days since parking at uni costs me heaps", c(W, FD))
s("N22", "the fewer days the better, I'm a mum and childcare is booked by the day", c(W, FD))
s("N23", "I'd rather have all my contact hours on fewer days, even if they're long, and I need lunch",
  c("I'd rather have all my contact hours on fewer days, even if they're long", FD),
  c("I need lunch", LU, DEF_LUNCH))
s("N24", "less days on campus pls and no 8am's",
  c("less days on campus pls", FD),
  c("no 8am's", BT, WK + " 0:00-9:00"))
s("N25", "Minimise how often I come in, I'm in Wollongong", c(W, FD))
s("N26", "I'm an elite athlete so I need fewer days at uni and nothing on Saturday mornings",
  c("I'm an elite athlete so I need fewer days at uni", FD),
  c("nothing on Saturday mornings", BT, "Sat 0:00-10:00"))
s("N27", "Cluster everything into as few days as possible, but no Wednesdays",
  c("Cluster everything into as few days as possible", FD),
  c("no Wednesdays", BT, "Wed all"))
s("N28", "I hate having one tiny class on a day by itself, I'd rather the days were full",
  c(W, FD, note="wants classes packed into fewer days; no count"))
s("N29", "I want no breaks between classes at all", c(W, LW))
s("N30", "a 1 hour break is fine but anything over 2 is too much", c(W, LW, note="gap lengths, not hours per day"))
s("N31", "Please don't leave me with huge holes in my day", c(W, LW))
s("N32", "I'd like my tutes straight after my lectures so I'm not killing time", c(W, LW))
s("N33", "Gaps make me procrastinate, so stack everything up together, and 3 days max",
  c("Gaps make me procrastinate, so stack everything up together", LW),
  c("3 days max", MD, 3))
s("N34", "When I have a free period I just end up going home and not coming back lol, so minimal gaps", c(W, LW))
s("N35", "no long waits between classes and I'd like an hour for lunch",
  c("no long waits between classes", LW),
  c("I'd like an hour for lunch", LU, "11:30-14:00 60"))
s("N36", "Don't want to be stuck on campus waiting for my next class for hours, I'd rather be at work", c(W, LW))
s("N37", "I'm autistic and unstructured time on campus is really hard for me, so back-to-back classes are best", c(W, LW))
s("N38", "classes close together, home by 4, no Fridays",
  c("classes close together", LW),
  c("home by 4", BT, WK + " 16:00-24:00"),
  c("no Fridays", BT, "Fri all"))
s("N39", "A gap here and there is ok but please no gaps over 90 minutes",
  c("A gap here and there is ok", OT),
  c("please no gaps over 90 minutes", LW))
s("N40", "I'd like 2 days a week on campus", c(W, MD, 2))
s("N41", "I can only realistically come in 3 days, my sister needs the car the other days", c(W, MD, 3))
s("N42", "4 days max, 3 if you can manage it", c(W, MD, 4, "real limit is the larger number"))
s("N43", "I want to come in once a week if that's even possible", c(W, MD, 1))
s("N44", "Three days on campus and that's it", c(W, MD, 3))
s("N45", "I need at least one weekday totally off, so 4 days max", c(W, MD, 4))
s("N46", "I'd like to do 2 days, I work 3 days a week in retail", c(W, MD, 2, "3 work days is a distractor"))
s("N47", "I'm doing 6 units this sem which is a lot but I still don't want more than 4 days",
  c(W, MD, 4, "6 units is a distractor"))
s("N48", "No more than 3 uni days, keep Mondays free and I'd prefer to finish by 5",
  c("No more than 3 uni days", MD, 3),
  c("keep Mondays free", BT, "Mon all"),
  c("I'd prefer to finish by 5", EL, "9:00-17:00"))
s("N49", "2 or 3 days is ideal", c(W, MD, 3, "real limit is the larger number"))
s("N52", "I'd love an actual lunch hour between 12 and 2", c(W, LU, "12:00-14:00 60"))
s("N53", "I need to eat at 11:30 because of my diabetes meds, give me till 12", c(W, LU, "11:30-12:00 30"))
s("N54", "my lunch needs to be 1 to 1:45", c(W, LU, "13:00-13:45 45"))
s("N55", "lunch break pls, 20 mins is enough", c(W, LU, "11:30-14:00 20"))
s("N56", "Make sure I've got time to grab food between classes around midday", c(W, LU, DEF_LUNCH))
s("N57", "I have to eat lunch with my meds at 12:30, half an hour", c(W, LU, "12:30-13:00 30"))
s("N58", "No classes 12-1 so I can eat", c(W, LU, "12:00-13:00 60", "eating -> lunch (rule 1)"))
s("N59", "No classes 12-1 cos that's when I do my shift at the uni cafe",
  c(W, BT, WK + " 12:00-13:00", "a lunchtime job without eating -> blocked_time"))
s("N60", "I need a meal break somewhere in the day, I'm on a 4 hour feeding schedule for my health",
  c(W, LU, DEF_LUNCH, "4 hour schedule is a distractor, not hours per day"))
s("N61", "Online classes are a no for me, I need the structure of being on campus", c(W, IP))
s("N62", "Don't put me in any online or hybrid classes", c(W, IP))
s("N63", "Face to face only, max 3 days, and nothing after 4pm",
  c("Face to face only", IP),
  c("max 3 days", MD, 3),
  c("nothing after 4pm", BT, WK + " 16:00-24:00"))
s("N64", "I want proper in-person classes, not recordings", c(W, IP))
s("N65", "My internet at home is shocking so please no online classes", c(W, IP))
s("N66", "I'm doing this degree to meet people so everything on campus pls", c(W, IP))
s("N67", "in person only and I want Dr Patel's tute if possible",
  c("in person only", IP),
  c("I want Dr Patel's tute if possible", OT))
s("N68", "zoom tutes are useless, give me real ones", c(W, IP))
s("N69", "Not too early, not too late, no gaps",
  c("Not too early", EL),
  c("not too late", EL),
  c("no gaps", LW))
s("N70", "I really struggle to function in the mornings", c(W, EL, note="ability, no request"))
s("N71", "I'm a shocker at getting up early, so the later the better", c(W, EL))
s("N72", "late classes make me miserable", c(W, EL))
s("N73", "Early morning lectures are a nightmare on the M5", c(W, EL, note="'early morning' is a modified part-of-day"))
s("N74", "Nothing super late in the evening pls, I'm catching two buses home",
  c(W, EL, note="'super late in the evening' is a modified part-of-day"))
s("N75", "I'd prefer my day to start at 10 at the earliest", c(W, EL, "10:00-18:00"))
s("N76", "If possible I'd like to be done by 3:30", c(W, EL, "9:00-15:30"))
s("N77", "Preferably classes from 9:30 to 4:30", c(W, EL, "9:30-16:30"))
s("N79", "I'm usually wrecked by the end of the day so late arvo classes aren't great", c(W, EL))
s("N80", "I'm on antidepressants that knock me out, so early starts are rough", c(W, EL))
s("N81", "I'd rather not start before 11 if I can help it", c(W, EL, "11:00-18:00"))
s("N82", "I'm slow in the mornings so ideally no 9ams",
  c(W, EL, "10:00-18:00", "hedged clock; a 9am class runs to 10, so classes from 10"))
s("N83", "Hopefully I can be finished by 4pm most days", c(W, EL, "9:00-16:00", "'hopefully' is a hedge (labels.HEDGES)"))
s("N84", "I'd prefer to start no earlier than 9 and finish by 5", c(W, EL, "9:00-17:00"))
s("N85", "I'd prefer to finish by 5 on Wednesdays", c(W, BT, "Wed 17:00-24:00", "weekday named: the hedge does not apply"))
s("N86", "I like having my classes in the morning so the arvo's free for work",
  c(W, BT, WK + " 12:00-18:00", "afternoon kept free for work"))
s("N87", "I want classes in the morning because I'm sharpest then", c(W, OT, note="wants mornings; no restriction"))
s("N88", "Evening classes suit me fine, honestly prefer them", c(W, OT, note="likes evenings; no request"))
s("N89", "Can I be in the same lab as my lab partner from last sem", c(W, OT))
s("N90", "I don't want to be in a class that's in the Wentworth building", c(W, OT, note="building"))
s("N91", "I'm hoping to get the tutor who speaks Mandarin", c(W, OT))
s("N92", "I need my exams to not be on the same day", c(W, OT, note="exams"))
s("N93", "Whatever's easiest for you guys", c(W, OT))
s("N94", "I'm a third year mech eng student doing my thesis this year", c(W, OT))
s("N95", "I want to get into the advanced stream", c(W, OT))
s("N97", "No preference on days or times, just want a good tutor", c(W, OT))
s("N98", "I'm a single mum so I can only do classes between 9:30 and 2:30",
  c(W, BT, WK + " 0:00-9:30; " + WK + " 14:30-24:00"))
s("N99", "No classes before 10 or after 6", c(W, BT, WK + " 0:00-10:00; " + WK + " 18:00-24:00"))
s("N100", "I tutor high schoolers Tues and Thurs 7 to 9pm", c(W, BT, "Tue,Thu 19:00-21:00"))
s("N101", "I have dialysis three times a week, Mon Wed Fri mornings",
  c(W, BT, "Mon,Wed,Fri 0:00-10:00", "'three times' is a distractor"))
s("N102", "I'm at my second job every weekday from 5", c(W, BT, WK + " 17:00-24:00"))
s("N103", "Tuesday all day and Thursday morning I'm busy", c(W, BT, "Tue all; Thu 0:00-10:00"))
s("N104", "Every Wednesday lunchtime I run a prayer group from 12 to 1",
  c(W, BT, "Wed 12:00-13:00", "lunchtime but no eating -> blocked_time"))
s("N105", "I'm on the uni rowing team so mornings are gone, and I want max 4 days",
  c("I'm on the uni rowing team so mornings are gone", BT, WK + " 0:00-10:00"),
  c("I want max 4 days", MD, 4))
s("N106", "Monday arvo, Wednesday arvo and all of Friday are blocked for work",
  c(W, BT, "Mon,Wed 12:00-18:00; Fri all"))
s("N107", "I start work at 3 every day so classes have to be done by then", c(W, BT, WK + " 15:00-24:00"))
s("N108", "I can't get to uni before 10:30 on Wednesdays, I drop my brother at a special school in Ryde",
  c(W, BT, "Wed 0:00-10:30"))
s("N109", "I have a standing appointment with my psychologist every Monday 4-5", c(W, BT, "Mon 16:00-17:00"))
s("N110", "No Tues no Thurs",
  c("No Tues", BT, "Tue all"),
  c("no Thurs", BT, "Thu all"))
s("N111", "I've got a disability support worker who comes Wednesday mornings till 11", c(W, BT, "Wed 0:00-11:00"))
s("N112", "keep Friday arvos free, I head down to see family in Canberra", c(W, BT, "Fri 12:00-18:00"))
s("N113", "I need to be off campus by 1pm on Thursdays for my shift", c(W, BT, "Thu 13:00-24:00"))
s("N114", "My church youth group is Friday nights and Sunday is church all day",
  c("My church youth group is Friday nights", BT, "Fri 18:00-24:00"),
  c("Sunday is church all day", BT, "Sun all"))
s("N115", "I teach at Hebrew school on Sunday mornings and Shabbat starts Friday evening so nothing after 4 on Fridays",
  c("I teach at Hebrew school on Sunday mornings", BT, "Sun 0:00-10:00"),
  c("Shabbat starts Friday evening so nothing after 4 on Fridays", BT, "Fri 16:00-24:00"))
s("N116", "I can do Mon and Tue only", c(W, BT, "Wed-Fri all", "only these days"))
s("N117", "I'm only available Wednesday to Friday", c(W, BT, "Mon,Tue all", "only these days"))
s("N118", "Any day but Thursday", c(W, BT, "Thu all"))
s("N119", "I'm in a wheelchair and the lifts in some buildings are slow, so I'd like extra time between classes",
  c(W, OT, note="wants gaps (opposite of less waiting); buildings"))
s("N120", "I've got jury duty on the 14th", c(W, OT, note="a calendar date, not a weekday or clock time"))
s("N121", "I need to be home by 3 on school days to pick up my twins, and I'd like a 3 day week",
  c("I need to be home by 3 on school days to pick up my twins", BT, WK + " 15:00-24:00"),
  c("I'd like a 3 day week", MD, 3))
s("N122", "I volunteer with the Rural Fire Service every second Tuesday and every Thursday night",
  c(W, BT, "Tue all; Thu 18:00-24:00", "alternate weeks -> whole day"))
s("N123", "Fortnightly on Mondays I have a uni committee meeting, so avoid Mondays", c(W, BT, "Mon all"))
s("N124", "I have rehab at 2pm on Tuesdays and Thursdays",
  c(W, BT, "Tue,Thu 14:00-24:00", "one afternoon clock -> X-24:00"))
s("N125", "My hospital shifts are 7am to 3pm on Saturdays", c(W, BT, "Sat 7:00-15:00"))
s("N126", "I can't do anything Thursday because I have my citizenship classes", c(W, BT, "Thu all"))
s("N127", "I teach dance Monday and Wednesday from 4:30", c(W, BT, "Mon,Wed 16:30-24:00"))
s("N128", "I'm doing a TAFE course on Tuesday nights and work Saturdays, otherwise I'm flexible",
  c("I'm doing a TAFE course on Tuesday nights", BT, "Tue 18:00-24:00"),
  c("work Saturdays", BT, "Sat all"),
  c("otherwise I'm flexible", OT))
s("N129", "The accessible bus only runs after 9:30, so nothing before 10",
  c(W, BT, WK + " 0:00-10:00", "9:30 is the reason; the request is 'before 10'"))
s("N130", "can I have my classes between 11 and 5, I need my mornings for my baby",
  c(W, BT, WK + " 0:00-11:00; " + WK + " 17:00-24:00", "commitment, so not a soft preference"))
s("N131", "I want to be done by 2:30 every day and no classes Monday",
  c("I want to be done by 2:30 every day", BT, WK + " 14:30-24:00"),
  c("no classes Monday", BT, "Mon all"))
s("N132", "Work Mon Tue 9-3, gym Thu 6am, and I want 4 hours of class max per day",
  c("Work Mon Tue 9-3", BT, "Mon,Tue 9:00-15:00"),
  c("gym Thu 6am", BT, "Thu 0:00-7:00", "one morning clock -> 0:00-(X+1)"),
  c("I want 4 hours of class max per day", MH, ("c", 4)))
s("N133", "I'm a postgrad with a research job Wednesdays and Fridays, and I don't want to be on campus for more than 8 hours on the other days",
  c("I'm a postgrad with a research job Wednesdays and Fridays", BT, "Wed,Fri all"),
  c("I don't want to be on campus for more than 8 hours on the other days", MH, ("s", 8)))
s("N134", "My son's therapy is Tuesday 3:30 so I have to leave uni by 2:45 that day",
  c(W, BT, "Tue 14:45-24:00", "the 3:30 appointment is the reason"))
s("N135", "Nothing in the arvo on Thursdays, nothing in the morning on Mondays",
  c("Nothing in the arvo on Thursdays", BT, "Thu 12:00-18:00"),
  c("nothing in the morning on Mondays", BT, "Mon 0:00-10:00"))
s("N136", "Please avoid my netball, Wednesday 6 till 8", c(W, BT, "Wed 18:00-20:00"))
s("N137", "I'd rather not have classes in the evenings because I'm scared walking to the station at night",
  c(W, BT, WK + " 18:00-24:00", "part-of-day word + request; the hedge does not apply"))
s("N139", "I've got a Pilates class Tues 7:30am and I'm free all day Wed if that helps",
  c("I've got a Pilates class Tues 7:30am", BT, "Tue 0:00-8:30"),
  c("I'm free all day Wed if that helps", OT))
s("N140", "I live with my grandparents and do their shopping Thursday mornings", c(W, BT, "Thu 0:00-10:00"))
s("N141", "Is it ok if I don't have anything scheduled Tuesday after 12", c(W, BT, "Tue 12:00-24:00"))
s("N142", "Mondays I'm at the hospital till 1 for my placement", c(W, BT, "Mon 0:00-13:00"))
s("N143", "Friday is my day off from work and I'd like to keep it that way, no uni", c(W, BT, "Fri all"))
s("N144", "I've got English classes at the community centre Tuesday and Thursday 9 to 12",
  c(W, BT, "Tue,Thu 9:00-12:00"))
s("N145", "I'd like to finish at 4 at the latest on Mondays and Tuesdays because of pickup",
  c(W, BT, "Mon,Tue 16:00-24:00"))
s("N146", "if you can, no classes after 5 on Friday so I can get to my shift", c(W, BT, "Fri 17:00-24:00"))
s("N147", "Ideally nothing before 9 on any day and Wednesdays off for my placement",
  c("Ideally nothing before 9 on any day", EL, "9:00-18:00", "'any day' is not a named weekday"),
  c("Wednesdays off for my placement", BT, "Wed all"))
s("N148", "I'd love to be in the same tute as my cousin and we both can't do Thursdays",
  c("I'd love to be in the same tute as my cousin", OT),
  c("we both can't do Thursdays", BT, "Thu all"))
s("N149", "I want my lab in the same building as my lecture, and no classes after 6",
  c("I want my lab in the same building as my lecture", OT),
  c("no classes after 6", BT, WK + " 18:00-24:00"))
s("N150", "I have a learning support plan that gives me extra exam time", c(W, OT))
s("N151", "No idea what I want tbh, just make it work", c(W, OT))
s("N152", "I'm doing a combined degree with law so I'll have some law classes too, can you check for clashes", c(W, OT))
s("N153", "My dog walking business runs 7 to 9am weekdays, and I'd like an hour for lunch, fewer days is better too",
  c("My dog walking business runs 7 to 9am weekdays", BT, WK + " 7:00-9:00"),
  c("I'd like an hour for lunch", LU, "11:30-14:00 60"),
  c("fewer days is better too", FD))
s("N155", "I'm a carer for my brother, he comes home at 3:15 so I need to be gone by 2:30, and I can do max 3 days",
  c("I'm a carer for my brother, he comes home at 3:15 so I need to be gone by 2:30", BT, WK + " 14:30-24:00"),
  c("I can do max 3 days", MD, 3))
s("N156", "Footy on Tuesday and Thursday nights, work Saturday, max 4 hours of class a day and an hour for lunch",
  c("Footy on Tuesday and Thursday nights", BT, "Tue,Thu 18:00-24:00"),
  c("work Saturday", BT, "Sat all"),
  c("max 4 hours of class a day", MH, ("c", 4)),
  c("an hour for lunch", LU, "11:30-14:00 60"))
s("N157", "I'd rather have everything in person, and keep my days to 6 hours of class max",
  c("I'd rather have everything in person", IP),
  c("keep my days to 6 hours of class max", MH, ("c", 6)))
s("N158", "I don't mind 8am starts, I just want to be home by 3",
  c("I don't mind 8am starts", OT),
  c("I just want to be home by 3", BT, WK + " 15:00-24:00"))
s("N159", "No more than 6 hours on campus per day, no more than 3 days a week, no gaps over an hour",
  c("No more than 6 hours on campus per day", MH, ("s", 6)),
  c("no more than 3 days a week", MD, 3),
  c("no gaps over an hour", LW))
s("N160", "I hate early starts and I hate gaps even more",
  c("I hate early starts", EL),
  c("I hate gaps even more", LW))
s("N162", "My mornings are for my baby so 11am at the earliest, and I'd like lunch around 1 to 2",
  c("My mornings are for my baby so 11am at the earliest", BT, WK + " 0:00-11:00"),
  c("I'd like lunch around 1 to 2", LU, "13:00-14:00 60"))
s("N163", "Classes on Monday and Tuesday only please, I go back to Bathurst for the rest of the week",
  c(W, BT, "Wed-Fri all", "only these days"))
s("N165", "Prefer 3 days but my main thing is no classes after 5",
  c("Prefer 3 days", MD, 3),
  c("my main thing is no classes after 5", BT, WK + " 17:00-24:00"))
s("N166", "I don't care about days, I care about not being on campus for 10 hour days, 7 max",
  c("I don't care about days", OT),
  c("I care about not being on campus for 10 hour days, 7 max", MH, ("s", 7), "10 is what they want to avoid; 7 is the limit"))
s("N167", "wanna be able to eat lunch at 12 for like 30 mins, and no gaps longer than 30 mins",
  c("wanna be able to eat lunch at 12 for like 30 mins", LU, "12:00-12:30 30"),
  c("no gaps longer than 30 mins", LW))
s("N168", "I'm Seventh-day Adventist so no Saturday anything, and I volunteer Wednesday arvos",
  c("I'm Seventh-day Adventist so no Saturday anything", BT, "Sat all"),
  c("I volunteer Wednesday arvos", BT, "Wed 12:00-18:00"))
s("N169", "My partner works nights so I'm home with the kids from 5",
  c(W, BT, WK + " 17:00-24:00", "the partner's nights are a reason; the block is from 5"))
s("N170", "I'm deaf and need an Auslan interpreter so in-person classes only, interpreters don't do Zoom well", c(W, IP))
s("N171", "I'd like as few days as possible, but not more than 7 hours of class on any of them",
  c("I'd like as few days as possible", FD),
  c("not more than 7 hours of class on any of them", MH, ("c", 7)))
s("N172", "Compact week, decent lunch break, no Friday",
  c("Compact week", FD),
  c("decent lunch break", LU, DEF_LUNCH),
  c("no Friday", BT, "Fri all"))
s("N173", "I work full time 9 to 5 Monday to Thursday, so classes outside those hours or on Friday",
  c(W, BT, "Mon-Thu 9:00-17:00"))
s("N174", "Max 2 days, no online, no 8ams, and an hour lunch",
  c("Max 2 days", MD, 2),
  c("no online", IP),
  c("no 8ams", BT, WK + " 0:00-9:00"),
  c("an hour lunch", LU, "11:30-14:00 60"))
s("N175", "I struggle with long days so 5 hrs of class max, and don't spread me over the whole week",
  c("I struggle with long days so 5 hrs of class max", MH, ("c", 5)),
  c("don't spread me over the whole week", FD))
s("N176", "Gaps between classes are a killer for my anxiety, I need classes back-to-back, and no more than 4 days",
  c("Gaps between classes are a killer for my anxiety, I need classes back-to-back", LW),
  c("no more than 4 days", MD, 4))
s("N177", "I commute from the Blue Mountains, about 2 hrs each way, so ideally just 2 days, nothing before 10",
  c("I commute from the Blue Mountains, about 2 hrs each way, so ideally just 2 days", MD, 2),
  c("nothing before 10", BT, WK + " 0:00-10:00"))
s("N178", "No 7pm classes, no Monday classes, no online classes",
  c("No 7pm classes", BT, WK + " 19:00-24:00"),
  c("no Monday classes", BT, "Mon all"),
  c("no online classes", IP))
s("N179", "Lunch from 12:30 to 1:30 and I'd like to be done by 4 if possible",
  c("Lunch from 12:30 to 1:30", LU, "12:30-13:30 60"),
  c("I'd like to be done by 4 if possible", EL, "9:00-16:00"))
s("N180", "I really don't like waiting around, and I really don't like mornings",
  c("I really don't like waiting around", LW),
  c("I really don't like mornings", EL, note="feeling about mornings, no request"))
s("N181", "I've got heaps of gaps in my current timetable and I hate it", c(W, LW))
s("N182", "no gaps no mornings no online",
  c("no gaps", LW),
  c("no mornings", BT, WK + " 0:00-10:00"),
  c("no online", IP))
s("N183", "I'm a caretaker at my church Tuesday and Thursday 6 to 8am, so on those days I'd prefer nothing before 10",
  c(W, BT, "Tue,Thu 0:00-10:00", "'those days' points back to Tue/Thu and the job, so the hedge does not apply"))
s("N184", "Could I avoid having classes on the days my kids are with me, which are Monday and Tuesday",
  c(W, BT, "Mon,Tue all"))
s("N185", "No early mornings, no late arvos, and lunch between 1 and 2",
  c("No early mornings", EL),
  c("no late arvos", EL),
  c("lunch between 1 and 2", LU, "13:00-14:00 60"))
s("N186", "Give me a timetable where I'm not on campus longer than 6 hours and I'm not waiting between classes",
  c("Give me a timetable where I'm not on campus longer than 6 hours", MH, ("s", 6)),
  c("I'm not waiting between classes", LW))
s("N187", "Mondays and Fridays I'm on placement at Westmead, and I'd like fewer days on campus overall",
  c("Mondays and Fridays I'm on placement at Westmead", BT, "Mon,Fri all"),
  c("I'd like fewer days on campus overall", FD))
s("N188", "keep tuesday free, keep thursday arvo free, keep it in person",
  c("keep tuesday free", BT, "Tue all"),
  c("keep thursday arvo free", BT, "Thu 12:00-18:00"),
  c("keep it in person", IP))
s("N189", "Fewer days and shorter gaps, that's all I ask",
  c("Fewer days", FD),
  c("shorter gaps, that's all I ask", LW))
s("N190", "I volunteer at Lifeline on Monday nights and Thursday nights, and I'd prefer to start after 10",
  c("I volunteer at Lifeline on Monday nights and Thursday nights", BT, "Mon,Thu 18:00-24:00"),
  c("I'd prefer to start after 10", EL, "10:00-18:00"))
s("N191", "The 8:05 bus is the only one that gets me there, so 9am classes are the earliest I can do",
  c(W, BT, WK + " 0:00-9:00", "9am is the earliest start; the bus time is a distractor"))
s("N192", "I'd love to have my lunch at the same time every day, 12 to 12:45", c(W, LU, "12:00-12:45 45"))
s("N193", "pls leave 1-2pm free on tues and thurs, I've got a standing zoom with my supervisor",
  c(W, BT, "Tue,Thu 13:00-14:00", "'zoom' here is a meeting, not online classes"))
s("N194", "Prefer online for lectures so I can rewatch them", c(W, OT, note="wants online classes"))
s("N195", "My kid's daycare closes at 5:30 and it's 40 mins away, so I need to leave by 4:45",
  c(W, BT, WK + " 16:45-24:00", "5:30 and 40 mins are the reason"))
s("N196", "Can I please not have any classes in the middle of the day on Wednesday, I've got a 12 to 2 shift",
  c(W, BT, "Wed 12:00-14:00"))
s("N197", "Uni sport on Wednesday afternoons, so no classes then", c(W, BT, "Wed 12:00-18:00"))
s("N198", "Wednesday is the only day I can't come", c(W, BT, "Wed all", "'only' names the one blocked day"))
s("N199", "Thursday's the only day I can come in", c(W, BT, "Mon-Wed,Fri all", "only this day"))
s("N200", "Only free on Mon, Tue and Fri this sem, and I'd like it in person",
  c("Only free on Mon, Tue and Fri this sem", BT, "Wed,Thu all"),
  c("I'd like it in person", IP))
s("N201", "I can do any day except Tues and Thurs mornings", c(W, BT, "Tue,Thu 0:00-10:00"))

# ---------------------------------------------------------------- set C
s("O1", "I'd like to be in the same tute as my best mate Liam, and I'd prefer to start after 10",
  c("I'd like to be in the same tute as my best mate Liam", OT),
  c("I'd prefer to start after 10", EL, "10:00-18:00"))
s("O2", "Not fussed about who teaches me, I just don't do well with early starts",
  c("Not fussed about who teaches me", OT),
  c("I just don't do well with early starts", EL))
s("O3", "I'm a mature age student, 38, coming back after a long break", c(W, OT, note="38 is an age"))
s("O4", "Can I get into a tute with other international students, and I'm happy with gaps",
  c("Can I get into a tute with other international students", OT),
  c("I'm happy with gaps", OT, note="gaps are fine; no request"))
s("O5", "I'm doing ENGG2112 and COMP2123 this sem, both have heaps of labs", c(W, OT))
s("O6", "I'd like to keep the same tutor I had in first year", c(W, OT))
s("O7", "Please make sure my lab and tute aren't on different campuses", c(W, OT, note="location"))
s("O8", "I want my exams as early as possible in the exam period so I can fly home to Shanghai", c(W, OT, note="exams"))
s("O9", "I don't really care about gaps or early classes, just put me with my friend Mei in the labs",
  c("I don't really care about gaps or early classes", OT),
  c("just put me with my friend Mei in the labs", OT))
s("O10", "Start times don't matter to me, but I've got a bad knee so I'd like my classes in buildings close to each other",
  c("Start times don't matter to me", OT),
  c("I've got a bad knee so I'd like my classes in buildings close to each other", OT, note="buildings"))
s("O11", "My only real wish is a tutor who explains things slowly", c(W, OT))
s("O12", "Days and times don't matter, I'm just happy to be here", c(W, OT))
s("O13", "I'm a second year doing engineering and commerce, and I'd rather not have 8am tutes",
  c("I'm a second year doing engineering and commerce", OT),
  c("I'd rather not have 8am tutes", EL, "9:00-18:00", "hedged clock, no day, no commitment; an 8am class runs to 9"))
s("O14", "I'd like Professor Wong for maths if possible, and no Tuesday classes because of work",
  c("I'd like Professor Wong for maths if possible", OT),
  c("no Tuesday classes because of work", BT, "Tue all"))
s("O15", "I want my tutorials to come after the lectures each week, and I can only do 3 days",
  c("I want my tutorials to come after the lectures each week", OT),
  c("I can only do 3 days", MD, 3))
s("O16", "Assignments are due Fridays so I'd like Thursday free to finish them",
  c(W, BT, "Thu all", "the assignment is the reason; the request names a weekday"))
s("O17", "I'm in the uni choir but rehearsal times haven't been set yet", c(W, OT, note="no time given"))
s("O18", "I'm pregnant and due in week 9, so I might need to switch to online later in the sem",
  c(W, OT, note="wants online; week 9 is not a weekday"))
s("O19", "I don't drive, so any time is fine as long as there's a bus", c(W, OT))
s("O20", "Last sem my timetable was perfect, can I just have the same days again", c(W, OT))
s("O21", "My shift finishes at 10 on Tuesdays so nothing before that",
  c(W, BT, "Tue 0:00-10:00", "'before that' points back to 10"))

# Candidates left out to hit the size and label mix (kept here so the build is reproducible).
DROP = set("E22,E25,E32,E41,E44,E59,E63,E64,E67,E76,E77,E86,E92,E97,E103,E107,E109,E110,E114,E117,E128,E132,E135,E141,E142,E149,E172,N99,N100,N102,N103,N107,N108,N109,N111,N112,N113,N117,N123,N125,N126,N127,N136,N140,N141,N142,N143,N144,N145,N146,N163,N184,N196,N197,E69,E83,E131,N40,N44,E29,E115,N10,N14,N16,E33,E52,E75,E102,E124,N52,N56,N192,E28,E82,E112,E121,N29,N31,N36,N181,N18,N21,N25,E72,N61,N62,N64,N66,N68,N93,N95,N150,N151".split(","))


def fmt_hours(value):
    return f"{value:g}"


def rows_for(sentence_id, sentence, clauses):
    rows, pos = [], 0
    for index, (text, label, val, note) in enumerate(clauses):
        text = sentence if text is None else text
        at = sentence.find(text, pos)
        if at < 0:
            raise SystemExit(f"{sentence_id}: clause not found in order: {text!r}")
        pos = at + len(text)
        row = {k: "" for k in ("sentence_id", "sentence", "clause", "label", "block", "max_days",
                               "max_class_hours", "max_campus_hours", "lunch", "prefer_hours", "note")}
        if index == 0:
            row["sentence_id"], row["sentence"] = sentence_id, sentence
        row["clause"], row["label"], row["note"] = text, label, note
        if label == BT:
            assert isinstance(val, str) and val, (sentence_id, text)
            row["block"] = val
        elif label == MD:
            assert isinstance(val, int), (sentence_id, text)
            row["max_days"] = str(val)
        elif label == MH:
            kind, hours = val
            row["max_class_hours" if kind == "c" else "max_campus_hours"] = fmt_hours(hours)
        elif label == LU:
            assert isinstance(val, str) and val, (sentence_id, text)
            row["lunch"] = val
        elif label == EL:
            row["prefer_hours"] = val or ""
        else:
            assert val is None, (sentence_id, text)
        rows.append(row)
    return rows


def main():
    keys = [k for k in DATA if k not in DROP]
    unknown = DROP - set(DATA)
    assert not unknown, unknown
    sentences = [DATA[k][0] for k in keys]
    dupes = [x for x, n in collections.Counter(sentences).items() if n > 1]
    assert not dupes, dupes
    random.Random(2112).shuffle(keys)
    out_rows = []
    labels = collections.Counter()
    sizes = collections.Counter()
    for number, key in enumerate(keys, start=1):
        sentence, clauses = DATA[key]
        rows = rows_for(f"e{number:03d}", sentence, clauses)
        out_rows += rows
        labels.update(r["label"] for r in rows)
        sizes[len(rows)] += 1
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)
    total = sum(labels.values())
    print("sentences", len(keys), "clauses", total)
    print("clauses per sentence", dict(sorted(sizes.items())),
          "multi share", round(sum(n for k, n in sizes.items() if k > 1) / len(keys), 3))
    for label, n in labels.most_common():
        print(f"  {label:22s} {n:4d}  {n / total:.1%}")


if __name__ == "__main__":
    main()
