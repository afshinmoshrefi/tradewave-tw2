# Daily AI Pick background rotation

The social-card generator selects a background from the persisted
`featured_date`, so a pick keeps the same design when it is regenerated.

| Day | Asset | Visual theme |
| --- | --- | --- |
| Monday | `daily-pick-card-bg-mon.png` | Indigo/cyan fresh-start wave |
| Tuesday | `daily-pick-card-bg-tue.png` | Cobalt/turquoise interlaced wave |
| Wednesday | `daily-pick-card-bg-wed.png` | Emerald/blue balanced crest |
| Thursday | `daily-pick-card-bg.png` | Original electric-blue market wave |
| Friday | `daily-pick-card-bg-fri.png` | Violet/magenta closing-week sweep |

Saturday and Sunday use the Thursday background as a safe fallback. The
production publisher normally runs only on weekdays.
