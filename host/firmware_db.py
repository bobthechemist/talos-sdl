# host_app/firmware_db.py

FIRMWARE_DATABASE = {
    808: {
        'manufacturer': 'Brockport Original Builds',
        'products': {
            810: 'Fake Device',
            811: 'Stirplate Manager', 
            812: 'Sidekick',
            813: 'Colorimeter'
        }
    },
    # 909: {
    #     'manufacturer': 'My Lab',
    #     'products': {
    #         909: 'Heater Control Unit',
    #     }
    # }
}

def get_device_name(vid: int, pid: int) -> str:
    """
    Looks up a human-readable name for a device based on its VID and PID.
    
    Returns a descriptive string or a default if not found.
    """
    manufacturer_info = FIRMWARE_DATABASE.get(vid)
    
    if not manufacturer_info:
        return "Unknown Manufacturer"
        
    product_name = manufacturer_info['products'].get(pid, "Unknown Product")
    manufacturer_name = manufacturer_info.get('manufacturer', "Unknown")
    
    return f"{product_name} ({manufacturer_name})"