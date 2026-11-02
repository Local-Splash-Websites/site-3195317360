# Forms

Every form posts to `/v1/lead`. Forms without Duda `label-dmform-*` fields are flagged; the lead service appends their fields as `Label: value` lines.

| Page | # | Shape | Fields | Labels |
|---|---|---|---|---|
| /contact | 0 | duda | 6 | FirstName, PhoneNumber, EmailAddress, StreetAddress, Message, DomainName |

**Unknown shapes:** 0
