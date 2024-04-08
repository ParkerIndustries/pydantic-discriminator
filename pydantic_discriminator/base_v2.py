from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, TypeVar

from pydantic import BaseModel, Field, TypeAdapter, model_serializer, model_validator
from pydantic._internal._model_construction import ModelMetaclass

from pydantic_discriminator.common import DiscriminatedBase, Naming


class DiscriminatedMeta(ModelMetaclass):
    def __new__(cls, name, bases, namespace, **kwargs):
        discriminator = kwargs.pop(Naming.DISCRIMINATOR_KWARG, name.lower())
        new_cls = super().__new__(cls, name, bases, namespace, **kwargs)
        setattr(new_cls, Naming.REGISTRY, {})
        setattr(new_cls, Naming.DISCRIMINATOR, discriminator)
        for base in bases:
            if hasattr(base, Naming.REGISTRY):
                getattr(base, Naming.REGISTRY)[discriminator] = new_cls
        return new_cls


_T = TypeVar("_T", bound="DiscriminatedBaseModel")


class DiscriminatedBaseModel(
    BaseModel, DiscriminatedBase[BaseModel], metaclass=DiscriminatedMeta
):
    type_: str = Field(alias=Naming.TYPE_FIELD_ALIAS, description="The type of model.")

    def __new__(cls: type[_T], *args, **kwargs) -> _T:
        if Naming.TYPE_FIELD_ALIAS not in kwargs:
            kwargs[Naming.TYPE_FIELD_ALIAS] = cls.discriminator()
        type_ = kwargs[Naming.TYPE_FIELD_ALIAS]
        if cls.discriminator() == type_:
            return super().__new__(cls)  # type: ignore
        registry = cls.get_registry_recur()
        if kwargs[Naming.TYPE_FIELD_ALIAS] not in registry:
            raise ValueError(
                f"Unknown discriminator {kwargs[Naming.TYPE_FIELD_ALIAS]} for {cls}"
            )
        other_cls = registry[kwargs[Naming.TYPE_FIELD_ALIAS]]
        return other_cls.__new__(other_cls, *args, **kwargs)  # type: ignore

    #! If the __new__ is called in rust, the redefined __new__ will not be called.
    #! But by simply adding a no-op constructor, the __new__ will be called as expected.
    #! This technique was condemned by the old ones.
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    @model_validator(mode="before")
    def _validate_type_field(cls, v):
        if Naming.TYPE_FIELD_NAME in v:
            v[Naming.TYPE_FIELD_ALIAS] = v.pop(Naming.TYPE_FIELD_NAME)
        if Naming.TYPE_FIELD_ALIAS not in v:
            v[Naming.TYPE_FIELD_ALIAS] = cls.discriminator()
        return v

    @model_serializer
    def serializer(self):
        # since we cannot call model_dump() to avoid a RecursionError
        return self._validate_type_field({
            key: TypeAdapter(field_info.annotation).validate_python(self.__dict__[key])
            for key, field_info in self.model_fields.items()
        })

    @classmethod
    def model_validate(
        cls: type[_T],
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
    ) -> _T:
        if isinstance(obj, MutableMapping) and Naming.TYPE_FIELD_NAME in obj:
            obj[Naming.TYPE_FIELD_ALIAS] = obj.pop(Naming.TYPE_FIELD_NAME)
        return super().model_validate(
            obj, strict=strict, from_attributes=from_attributes, context=context
        )
