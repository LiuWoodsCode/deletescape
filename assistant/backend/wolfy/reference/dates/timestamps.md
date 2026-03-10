# Timestamps & ISO8601

### **ISO8601**

[ISO8601](https://en.wikipedia.org/wiki/ISO_8601) is an international standard for formatting dates & time&#x73;**,** often used by databases.&#x20;

Use "as iso8601" to convert into this format:

```
April 1, 2019 3:30pm as iso8601               | 2019-04-01T15:30:00+11:00
```

Use "to date" to convert into a regular date format:

```
2019-04-01T15:30:00 to date                   | 1 April 2019 at 3:30 pm
```

### **Timestamps**

[Unix time](https://en.wikipedia.org/wiki/Unix_time) is a system for describing a moment in tim&#x65;**,** often used in programming. A timestamp is the number of seconds that have passed since the "reference date" (January 1st, 1970).

```
April 1, 2019 to timestamp               | 1554109200
1559740303.48 to date                    | 5 June 2019 at 11:11 pm
```

To get a timestamp for the present moment, use **current timestamp**

```
current timestamp                         | 1559740303.48
```

#### **Millisecond timestamps**

You can convert millisecond timestamps into dates as well

```
1733823083000 to date                         | 10 December 2024 at 8:31:23 pm
```
