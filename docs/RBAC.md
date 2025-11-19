# RBAC

python manage_rbac.py init
python manage_rbac.py list-roles
python manage_rbac.py list-permissions
python manage_rbac.py show-role superadmin
python manage_rbac.py add-permission "report.generate" "Generate reports"
python manage_rbac.py add-role "moderator" "user.read,user.update,session.terminate"
python manage_rbac.py assign-role tim admin