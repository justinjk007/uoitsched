#! /usr/bin/env python3
from bs4 import BeautifulSoup
from ics import Calendar, Event
import requests
from datetime import datetime, timedelta, date
import weekday

lookup_table = {}

def timezone_offset(date_):
    dst_start = datetime(date_.year, 3, 8, 2, 0)
    dst_start += timedelta(6 - dst_start.weekday())
    dst_end = datetime(date_.year, 11, 1, 2, 0)
    dst_end += timedelta(6 - dst_end.weekday())
    return 4 if dst_start.date() <= date_ < dst_end.date() else 5

def parse_schedule(soup):
    # There is a single CRN tag associated with every course, so we can use it to find all the info for each course.
    crn_tags = [ac.parent.findNext('td') for ac in soup.findAll('acronym')]

    events = []
    warnings = []

    for crn in crn_tags:
        # td < tr < table
        meta_table = crn.parent.parent
        course_title, course_code, course_section = meta_table.find(
            'caption').string.split(' - ')

        # Week, Type, Time, Days, Where, Date Range, Schedule Type, Instructors
        times_table = [list(tr.findAll('td'))
                       for tr in meta_table.findNext('table').findAll('tr')[1:] if meta_table.findNext('table').find('caption').string == "Scheduled Meeting Times"]
        for row in times_table:
            times, day, location, dates, kind, instructor = [
                td.string.replace('\xa0', '') if td.string else '' for td in row][1:]
            try:
                start_time, end_time = (datetime.strptime(
                    time_string, "%I:%M %p") for time_string in times.split(' - '))
                start_date, end_date = (datetime.strptime(
                    date_string, "%b %d, %Y") for date_string in dates.split(' - '))
                if not start_date or not end_date or not start_time or not end_time:
                    raise ValueError('start or end date/time not defined')
            except ValueError:
                warnings += ['Course does not have an assigned meeting time: ' +
                             course_title + ' ' + kind]
                continue
            class_dates = weekday.weekday_range(start_date, end_date, day)
            for date_ in class_dates:
                datetime_ = datetime(
                    year=date_.year, month=date_.month, day=date_.day)
                start_datetime = datetime_ + timedelta(hours=start_time.hour + timezone_offset(
                    date_), minutes=start_time.minute, seconds=start_time.second)
                end_datetime = datetime_ + timedelta(hours=end_time.hour + timezone_offset(
                    date_), minutes=end_time.minute, seconds=end_time.second)
                event = Event(begin=start_datetime, end=end_datetime)
                event.name = course_title + ' ' + kind
                event.location = location.split()[-1]
                event.description = 'CRN: %s\nCourse Code: %s\nSection: %s\nInstructor:%s\n' % (
                    crn.string, course_code, course_section, instructor)
                events += [event]

    return events, warnings


def get_schedule(username, password, start_date):
    payload = {
        'user': username,
        'pass': password,
        'uuid': '0xACA021'
    }
    with requests.Session() as request_session:
        print("logging in as %s" % payload['user'])
        request_session.post(
            'https://portal.mycampus.ca/cp/home/login', data=payload)
        detail_url = 'https://ssbp.mycampus.ca/prod_uoit/bwskfshd.P_CrseSchdDetl'
        request_session.get(
            'https://portal.mycampus.ca/cp/ip/login?sys=sct&url=' + detail_url)
        r = request_session.post(
            detail_url, data={'term_in': start_date.strftime('%Y%m')})
        soup = BeautifulSoup(r.text, 'html.parser')
        if soup.find('title').string == 'User Login':
            return False, []
        events, warnings = parse_schedule(soup)
        calendar = Calendar(events=events)
        return calendar, warnings
