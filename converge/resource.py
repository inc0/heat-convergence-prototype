from .framework import datastore
from .stack import stack_resources, get_stack_resource_by_name
from .template import GetAtt, GetRes


resources = datastore.Datastore(
    'Resource',
    'key',
    'phys_id',
    'name',
    'properties',
    'state',
    'version',
    'prop_refs',
)


class Resource(object):
    """
    This class simulates "real resources", therefore it has no notion of
    dependency here. Statuses and dependency checks in create/delete/update are
    for validation purposes
    """
    def __init__(self, key):
        self.key = key
        self.data = resources.read(key)

    @staticmethod
    def update_or_create(key=None, **data):
        state = 'COMPLETE'
        if not Resource.check_create_readiness(data['name']):
            state = 'ERROR'
        prop_refs = []
        for prop, prop_value in data['properties'].iteritems():
            if type(prop_value) == GetRes:
                source = resources.read(
                    resources.find(
                        name=prop_value.target_name,
                    ).next()
                )
                data['properties'][prop] = source.phys_id
            if type(prop_value) == GetAtt:
                source = resources.read(
                    resources.find(
                        name=prop_value.target_name,
                    ).next()
                )
                data['properties'][prop] = source.properties[prop_value.attr]
                prop_refs.append({
                    'resource': source.name,
                    'version': source.version,
                })
        resource = {
            'name': data['name'],
            'properties': data['properties'],
            'state': state,
            'phys_id': '{}_phys_id'.format(data['name']),
            'prop_refs': prop_refs,
        }
        if key is not None:
            resource.update({'key': key})
            current_version = resources.read(key).version
            resources.update(version=current_version + 1, **resource)
        else:
            resources.create(version=1, **resource)

    def delete(self):
        if not Resource.check_delete_readiness(self.data.name):
            resources.update(key=self.key, state="ERROR")
            return
        resources.delete(self.key)
        stack_res = get_stack_resource_by_name(self.data.name)
        stack_resources.update(key=stack_res.key, state="DELETE")

    @staticmethod
    def check_create_readiness(res_name):
        """
        This is logic we might potentially have to implement in resource api.
        Resource objects should have methods to determine if all dependencies
        for actions have been met
        """
        equivalent = get_stack_resource_by_name(res_name)
        for dependency_name in equivalent.depends_on:
            try:
                dependency = stack_resources.read(
                    resources.find(name=dependency_name).next()
                )
            except StopIteration:
                dependency = None
            if not dependency or dependency.state != 'COMPLETE':
                return False
        return True

    @staticmethod
    def check_delete_readiness(res_name):
        all_stack_names = set(
            map(
                lambda r: r.name,
                stack_resources._store.itervalues(),
            )
        )
        for resource_name in all_stack_names:
            res = get_stack_resource_by_name(resource_name)
            if res_name in res.depends_on and res.state != "DELETE":
                return False
        return True

    @staticmethod
    def check_update_required(res_name):
        equivalent = get_stack_resource_by_name(res_name)
        res = Resource.get_by_name(res_name)
        if equivalent.properties.keys() != res.data.properties.keys():
            return True
        for prop_ref in res.data.prop_refs:
            dependency = Resource.get_by_name(prop_ref['resource'])
            if dependency.data.version != prop_ref['version']:
                return True
        for prop_key, prop_value in equivalent.properties.iteritems():
            if all((
                (type(prop_value) == str),
                (res.data.properties[prop_key] != prop_value),
            )):
                return True
        return False

    @classmethod
    def get_by_name(cls, res_name):
        res_ds = resources.read(
            resources.find(
                name=res_name,
            ).next()
        )
        return cls(key=res_ds.key)
