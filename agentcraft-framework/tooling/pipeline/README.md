# Pipeline

`Pipeline([first, second])(data)` returns `second(first(data))`.

```python
from pipeline import Pipeline

pipeline = Pipeline([
	lambda data: data["values"],
	sum,
	lambda total: {"doubled": total * 2},
])

result = pipeline({"values": [1, 2, 3]})
assert result == {"doubled": 12}
```

Each function accepts one value and returns the next. Use a dictionary or tuple for
multiple inputs. A pipeline is itself callable, so pipelines can be nested and reused.
The function list is captured at construction. An empty pipeline returns its input
unchanged. Exceptions propagate immediately; subsequent functions do not run.

Synchronous only. Inputs are passed directly, not copied; functions may mutate them.
No configuration engine, retries, storage, or service dependencies.
