# Video Timecode & Frame Rates

A timecode is quantity of time in the format hour:minute:second:frames, commonly used in video editing. You should specify your desired frame rate (fps) when creating a timecode.&#x20;

You can add/remove units of time or frames from a timecode

```
03:10:20:05 at 30 fps + 50 frames                     | 03:10:21:25  
00:10:20:50 @ 60 fps + 10 minutes                     | 00:20:20:50 
3h 2m 25s 10 frames at 24 fps + 1 hour 12 minutes     | 04:14:25:10
```

Or covert a timecode into a quantity of frames, or from a quantity of frames into a timecode

```
00:30:10:00 @ 24 fps in frames                        | 43,440 frames
43,440 frames @ 24 fps                                | 00:30:10:00
```

Add timecodes together, and subtract them from each other

```
03:10:20:05 @ 30 fps + 03:10:20:010                   | 06:20:40:15
03:10:20:05 at 12 fps - 00:20:35:00                   | 02:49:45:05
```

{% hint style="info" %}
• When adding or subtracting timecodes, you only need to specify the desired frame rate for one of the time codes in the operation

• The other timecode will use the specified frame rate automatically
{% endhint %}

{% hint style="info" %}
• If you do not specify a desired frame rate when creating a timecode, a default frame rate of **24 fps** (commonly used in film production) will be used&#x20;

• You can override the default frame rate by defining a **global variable** defined in terms of **fps**

![](https://1915029247-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F-Lf0gWBnuB8M1SitWhyk%2Fuploads%2FNkPHIptWF00p5tE2gI72%2FGlobal%20frame%20rate%20variable.png?alt=media\&token=61d1d90c-5478-452f-92be-062ccb7804b0)
{% endhint %}

### Frames and fps

Perform calculations using frames and fps (frames/second) units

```
30 fps × 3 minutes                     | 5,400 frames
15.6k frames / 24 fps                  | 650 s
```
