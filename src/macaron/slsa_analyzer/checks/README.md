# Defining Checks

The checks defined in this directory are automatically loaded during the startup of Macaron and used during the analysis. This `README.md` shows how a Check can be created.

## Base Check
The `BaseCheck` class (located at [base_check.py](./base_check.py)) is the abstract class to be inherited by other concrete checks.
Please see [base_check.py](./base_check.py) for the attributes of a `BaseCheck` instance.

## Writing a Macaron Check
These are the steps for creating a Check in Macaron:
1. Create a module with the name `<name>_check.py`. Note that Macaron **only** loads check modules that have this name format.
2. Create a class that inherits `BaseCheck` and initiates the attributes of a `BaseCheck` instance.
3. Register the newly created Check class to the Registry ([registry.py](../registry.py)). This will make the Check available to Macaron. For example:
```python
from macaron.slsa_analyzer.registry import registry

# Check class is defined here
# class ExampleCheck(BaseCheck):
#     ...

registry.register(ExampleCheck())
```
4. Add an ORM mapped class for the check facts so that the policy engine can reason about the properties. To provide the mapped class, all you need to do is to add a class that inherits from `CheckFacts` class and add the following attributes (rename the `MyCheckFacts` check name and `__tablename__` as appropriate).

```python
class MyCheckFacts(CheckFacts):
    """The ORM mapping for justifications in my check."""

    __tablename__ = "_my_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The name of the column (property) that becomes available to policy engine.
    my_column_name: Mapped[str] = mapped_column(String, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "_my_check",
    }
```

For more examples, please see the existing Checks in [checks/](./).
