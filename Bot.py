def get_open_interest():
    response = get_futures_analytics(
        FUTURES_SYMBOL,
        "open-interest",
        3600
    )

    # Временно возвращаем сырой ответ,
    # чтобы увидеть реальную структуру Kraken API.
    raise Exception(
        "RAW OI: " +
        str(response)[:2500]
    )


def get_funding():
    response = get_futures_analytics(
        FUTURES_SYMBOL,
        "funding",
        3600
    )

    # Временно возвращаем сырой ответ,
    # чтобы увидеть реальную структуру Kraken API.
    raise Exception(
        "RAW FUNDING: " +
        str(response)[:2500]
    )
