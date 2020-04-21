import click
from virl.api import VIRLServer
from virl2_client import ClientLibrary
from virl import __version__

@click.command()
def version():
    """
    version information
    """
    server = VIRLServer()
    client = ClientLibrary(server.host, server.user, server.passwd, ssl_verify=False)
    server_version = "Unknown"
    try:
        response = client.session.get(client._base_url + "system_information")
        response.raise_for_status()
        server_version = response.json()["version"]
    except:
        pass
    virlutils_version = __version__
    click.secho("virlutils Version: {}".format(virlutils_version))
    click.secho("CML Controller Version: {}".format(server_version))


@click.command()
def version1():
    """
    version information
    """
    server = VIRLServer()
    virlutils_version = __version__
    server_version = server.get_version().get('virl-version')
    click.secho("virlutils Version: {}".format(virlutils_version))
    click.echo("VIRL Core Version: {}".format(server_version))
