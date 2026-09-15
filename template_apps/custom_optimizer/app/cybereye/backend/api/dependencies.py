from typing import Annotated

from fastapi import Depends

from ..security import Principal, current_principal

Caller = Annotated[Principal, Depends(current_principal)]