class UsuariosSeguroController < ApplicationController
  def busca
    @usuarios = User.where(nome: params[:nome])
    render json: @usuarios
  end
end
