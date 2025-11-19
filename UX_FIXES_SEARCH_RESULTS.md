# UX Fixes: Search Results

## Problem
The user reported that the search results (offer cards) looked "ugly", lacked photos, and had little information.

## Solution
1.  **Data Layer**:
    -   Updated `OfferListItem` dataclass in `app/services/offer_service.py` to include a `photo` field.
    -   Updated `_to_offer_list_item` mapper to extract the photo ID from the database result (index 8).

2.  **Presentation Layer**:
    -   Updated `handlers/search.py` to use `app.templates.offers.render_offer_card` for generating the caption. This ensures the search result card matches the standard offer card format (including address, delivery info, stock, expiry date).
    -   Modified `handlers/search.py` to check for the presence of a photo.
    -   If a photo exists, the bot now uses `message.answer_photo` instead of `message.answer`.

## Files Changed
-   `app/services/offer_service.py`
-   `handlers/search.py`

## Verification
-   Search results should now display the product image if available.
-   The caption should be well-formatted with emojis and detailed information.
