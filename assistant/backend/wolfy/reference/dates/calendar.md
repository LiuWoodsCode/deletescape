# Calendar Calculations

### Adding or subtracting time from dates

```
10 June + 3 weeks                          | 1 July
April 1, 2019 − 3 months 5 days            | 25 December 2018

12/02/1988 + 32 years                      | 12 February 2020
01.05.2005 + 3 years 2 months 3 weeks      | 22 July 2008

3 weeks after March 14, 2019               | 4 April 2019
28 days before March 12                    | 12 February
2 months 3 days after June 5               | 8 August

yesterday - 8 weeks 3 days                 | 12 July
Yesterday + 1 week                         | 11 June
```

### Getting a date relative to the present

```
today + 3 weeks                     | 1 October
now − 1 month                       | 5 May

4 days from now                     | 14 September
3 days ago                          | 7 September
```

### **Find the amount of time between two dates**

```
January 10 - February 5             | 3 weeks 5 days

3 March to 30 May                   | 2 months 3 weeks 6 days

days since July 15                  | 57 days
days till December 25               | 106 days
days between 3 March and 30 May     | 88 days

1978 to 2021                        | 42 years

Monday - Friday                     | 4 days
```

{% hint style="info" %}
Intervals of time are calculated from midday on the first date midday to midday on the last date in the interval.&#x20;

Use the inclusive interval function if you want to include both the starting and ending date in the interval (see [below](#inclusive-intervals-of-time-1))
{% endhint %}

### Inclusive intervals of time between two dates <a href="#inclusive-intervals-of-time" id="inclusive-intervals-of-time"></a>

```
Monday through Friday                | 5 days
April 1 through April 30 in days     | 30 days
```

### Week numbers (ISO 8601)

```
week of year                                   | 36
week number on march 12, 2021                  | 10
```

### **How many days in a month or quarter**

```
days in Q3                         | 92 days
days in February 2020              | 29 days
```

### Find the midpoint between two dates

```
midpoint between March 12 and April 5        | 24 March    
halfway between today and next Thursday      | 13 September
```

## Notes on Ambiguity in Calendar Calculations

**Ambiguous months**

Unlike days and weeks, months are not clearly defined in terms of seconds. Soulver attempts to do the most logical thing given the expression. It's smart at taking into account leap years, and other calendar peculiarities:

```
Feb 28 + 1 month                           | 28 March
January 31 2020 + 1 month                  | February 29 2020
```

**Dates with unspecified years**

A date without the year specified may use either the current year or the following year.

```
# In December 2019

// next year is assumed, as the nearest January is in the future
January 12 + 3 weeks                       | 2 February 2020

// this year is assumed, as the month is still recently in the past
November 1 - 5 days                        | 27 October 2019
```
