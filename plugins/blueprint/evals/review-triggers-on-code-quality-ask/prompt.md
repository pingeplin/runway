---
max_turns: 4
runs: 3
timeout_seconds: 240
tags: [triggering, routing]
allowed_tools: [Read, Glob, Grep, Skill]
---

Something about this feels off to me but I can't put my finger on it:

```python
def apply_discount(order, code):
    if code == "SAVE10":
        order.total = order.total * 0.9
    elif code == "SAVE20":
        order.total = order.total * 0.8
    elif code == "HALF":
        order.total = order.total * 0.5
    else:
        pass
    order.discount_applied = True
    return order
```

What do you think?
