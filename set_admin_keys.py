import frappe

def run():
    usr = frappe.get_doc('User', 'Administrator')
    usr.api_key = 'test_api_key'
    usr.set_api_secret('test_api_secret')
    usr.save(ignore_permissions=True)
    frappe.db.commit()
    print("Successfully set API keys for Administrator!")

if __name__ == '__main__':
    run()
